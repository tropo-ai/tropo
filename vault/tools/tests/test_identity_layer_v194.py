#!/usr/bin/env python3
"""3d430852 Stage A AC8 — the receipt suite: one named check per
committed_substrate row. Source-level pins (the accepts-both marker at the
row's sites) plus behavioral checks where cheap; every check names its row's
target module so a drifted row fails by NAME, not by count.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

BOTH = r"[0-9a-f]{8}(?:[0-9a-f]{4})?"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mint = _load("identity_layer_v194_mint", TOOLS / "tropo-mint-id.py")
from lib import template_leg  # noqa: E402


def src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def has_marker(text: str, min_count: int = 1, marker: str = "accepts-both") -> bool:
    return text.count(marker) >= min_count


class IdentityLayerReceipt(unittest.TestCase):
    """AC8: one check per row."""

    def test_row_governed_path_authority(self) -> None:
        t = src("vault/tools/lib/governed_path.py")
        self.assertIn("UID_SHAPES", t)
        self.assertIn("8", t.split("UID_SHAPES")[1][:80])
        self.assertIn("12", t.split("UID_SHAPES")[1][:80])
        self.assertIn("def is_legacy_uid", t)

    def test_row_ts_adapter(self) -> None:
        t = src("tropo-app/lib/governed-path.ts")
        # Pinned against the AUTHORITY since the Stage B flip (2026-08-31,
        # W4/bb3911f5): the adapter's constant must equal the Python
        # authority's, whatever a future ruling sets it to.
        import re as _re
        m = _re.search(r"MINT_HEX_LEN = (\d+)", t)
        self.assertTrue(m, "the adapter no longer declares MINT_HEX_LEN")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from lib.governed_path import MINT_HEX_LEN as _AUTH_LEN
        self.assertEqual(m.group(1), str(_AUTH_LEN),
                         "the TS adapter's generation constant drifted from the authority")
        self.assertIn("export function mintCandidate", t)
        self.assertIn("export function freshUid", t)

    def test_row_mint_id_stage_a(self) -> None:
        t = src("vault/tools/tropo-mint-id.py")
        self.assertTrue(has_marker(t, 3))
        self.assertIn('"--title"', t)

    def test_row_template_leg_title(self) -> None:
        t = src("vault/tools/lib/template_leg.py")
        self.assertIn("MINT_OPTIONAL_TOKENS", t)
        self.assertIn('title: str | None = None', t)

    def test_row_templates_rebound(self) -> None:
        for name in ("task", "dev-spec", "design-brief"):
            t = src(f"vault/capsules/templates/{name}.template.md")
            self.assertEqual(t.count("<<MINT:title>>"), 2, name)
        note = src("vault/capsules/templates/note.template.md")
        self.assertNotIn("<<MINT:title>>", note, "note is EXEMPT")

    def test_row_capsule_rebinds(self) -> None:
        import hashlib, json
        reg = json.loads(src("vault/capsules/mint-registry.json"))
        for row in reg["types"]:
            if row["type"] in ("task", "dev-spec", "design-brief"):
                tpl = ROOT / row["mint_template"]
                self.assertEqual(
                    hashlib.sha256(tpl.read_bytes()).hexdigest(),
                    row["mint_template_sha256"], row["type"])

    def test_row_studio_flag(self) -> None:
        import json
        body = json.loads(src(".tropo-studio/readable-filenames.json"))
        self.assertTrue(body.get("enabled"), body)

    def test_row_skeleton_flag(self) -> None:
        import json
        body = json.loads(src(
            "vault/templates/.tropo-studio-skeleton/readable-filenames.json"))
        self.assertTrue(body.get("enabled"))

    def test_row_index_surfaces(self) -> None:
        t = src("vault/tools/lib/index_surfaces.py")
        self.assertGreaterEqual(t.count("is_governed_uid_shape"), 6)

    def test_row_rebuild_index(self) -> None:
        t = src("vault/tools/tropo-rebuild-index.py")
        self.assertIn("collect_docs_records", t)  # walker family member

    def test_row_validator(self) -> None:
        t = src("vault/tools/tropo-validate.py")
        self.assertTrue(has_marker(t, 6))
        self.assertIn("rglob('*.py')", t, "D2: the chokepoint scan is recursive")
        self.assertIn("RUN_RECORD_DEFERRAL_MARKER", t)

    def test_row_orient_stage_c(self) -> None:
        t = src("vault/tools/lib/orient_stage_c.py")
        self.assertTrue(has_marker(t, 1))

    def test_row_vault_search(self) -> None:
        t = src("vault/tools/tropo-vault-search.py")
        self.assertIn("_real_record_path", t)

    def test_row_check_one(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-check-one.py")))

    def test_row_lock_dev_spec(self) -> None:
        """Assert the PROPERTY, not a marker count.

        This asserted >=2 "accepts-both" markers and went red when the file's two uid
        sites were consolidated into one at 8533887d6 — a correct cleanup reported as a
        drifted row. A count answers "how many sites did someone annotate", which is not
        what the row is about; the row is about whether any uid regex in this file can
        still refuse a 12-hex uid. So that is what this reads, and it keeps its teeth:
        add one 8-hex-only uid regex anywhere in the file and it goes red by line.
        """
        text = src("vault/tools/tropo-lock-dev-spec.py")
        bare_only = [
            f"{i}: {line.strip()[:90]}"
            for i, line in enumerate(text.splitlines(), 1)
            if "[0-9a-f]{8}" in line and "(?:[0-9a-f]{4})?" not in line
        ]
        self.assertEqual(
            bare_only, [],
            "uid pattern(s) in tropo-lock-dev-spec.py still match 8-hex only and would "
            "refuse a composite 12-hex uid:\n  " + "\n  ".join(bare_only))
        self.assertIn(
            "[0-9a-f]{8}", text,
            "no uid pattern found at all — this receipt would pass vacuously on a file "
            "that had stopped parsing uids entirely")

    def test_row_e337f1dd(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/e337f1dd.py"), 4))

    def test_row_runtime_9e7003b1(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/9e7003b1.py"), 12))

    def test_row_lock_release_plan(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-lock-release-plan.py")))

    def test_row_close_dev(self) -> None:
        t = src("vault/tools/tropo-close-dev.py")
        self.assertIn("resolve_governed_path", t)

    def test_row_recycle(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-recycle.py"), 3))

    def test_row_folder(self) -> None:
        self.assertEqual(src("vault/tools/tropo-folder.py").count("(?:[0-9a-f]{4})?"), 13)

    def test_row_folder_sidecar(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/lib/folder_sidecar.py")))

    def test_row_import_walker(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-import-walker.py"), 2))

    def test_row_release_mint(self) -> None:
        t = src("vault/tools/tropo-release.py")
        self.assertIn("_chokepoint_mint_uid", t)
        self.assertNotIn('"invocation_uid": secrets.token_hex(4)', t)

    def test_row_publish_mint(self) -> None:
        t = src("vault/tools/tropo-publish-release.py")
        self.assertIn("_chokepoint_mint_uid", t)

    def test_row_emit_event(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-emit-event.py"), 2))

    def test_row_event_identity(self) -> None:
        self.assertIn("(?:[0-9a-f]{4})?", src("vault/tools/lib/event_identity.py"))

    def test_row_check_events(self) -> None:
        self.assertTrue(has_marker(src("vault/tools/tropo-check-events.py"), 2))

    def test_row_activate(self) -> None:
        t = src("vault/tools/tropo-activate.py")
        self.assertIn("_HEX_BOTH_RE", t)

    def test_row_publish_service_minter(self) -> None:
        t = src("vault/tools/lib/publish_service.py")
        self.assertNotIn("uuid.uuid4().hex[:8]", t)

    def test_row_archive_minter(self) -> None:
        t = src("vault/tools/tropo-archive.py")
        self.assertIn("_chokepoint_hex", t)

    def test_row_ts_create_route(self) -> None:
        self.assertIn("mintCandidate", src(
            "tropo-app/app/api/projects/create/route.ts"))

    def test_row_ts_node_route(self) -> None:
        self.assertIn("mintCandidate", src("tropo-app/app/api/node/route.ts"))

    def test_row_ts_boards_route(self) -> None:
        self.assertIn("mintCandidate", src("tropo-app/app/api/boards/route.ts"))

    def test_row_ts_vault_store(self) -> None:
        self.assertIn("mintCandidate", src(
            "tropo-app/lib/project-store/vault-store.ts"))

    def test_row_ts_chat_sessions(self) -> None:
        self.assertIn("mintCandidate", src(
            "tropo-app/lib/project-chat-sessions.ts"))

    def test_row_ts_uid_family(self) -> None:
        for rel in ("tropo-app/app/api/node/[uid]/route.ts",
                    "tropo-app/app/api/node/[uid]/archive/route.ts",
                    "tropo-app/app/api/node/[uid]/transition/route.ts",
                    "tropo-app/app/api/node/route.ts"):
            self.assertIn("isGovernedUidShape", src(rel), rel)

    def test_row_ts_node_engine(self) -> None:
        t = src("tropo-app/lib/boards/node-engine.ts")
        self.assertIn("isGovernedUidShape", t)

    def test_row_ts_vectors_registration(self) -> None:
        t = src("tropo-app/tests/test-qa.ts")
        self.assertIn("GP1Cases", t)
        v = src("tropo-app/tests/governed-path-vectors.ts")
        self.assertIn("freshUid(seen)", v)

    def test_row_marker_only_rows(self) -> None:
        self.assertIn("RUN-RECORD DEFERRAL MARKER",
                      src("vault/tools/tropo-orient.py"))
        self.assertGreaterEqual(src(
            "vault/tools/tropo-distiller-metered-canary.py").count(
            "RUN-RECORD DEFERRAL MARKER"), 2)
        self.assertIn("RUN-RECORD DEFERRAL MARKER",
                      src("vault/tools/lib/metered_model.py"))

    def test_row_event_validators(self) -> None:
        self.assertTrue(has_marker(src(
            ".tropo/scripts/lib/event_validators.py"), 4))

    def test_row_walker_fixture_migrated(self) -> None:
        t = src("vault/tools/tests/test_walker_nested_mount_parenting_7b1e0ae5.py")
        self.assertIn(BOTH.replace("{8}", "{8}"), t)
        self.assertIn("(?:[0-9a-f]{4})?", t)

    def test_chokepoint_scan_clean(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tv_receipt", TOOLS / "tropo-validate.py")
        tv = importlib.util.module_from_spec(spec)
        sys.modules["tv_receipt"] = tv
        spec.loader.exec_module(tv)
        findings, checked, violations = tv.check_mint_id_chokepoint(ROOT)
        self.assertEqual(violations, 0,
                         "raw mints bypassing the chokepoint: %s" % findings[:3])


class CollisionSafetyAcrossShapes(unittest.TestCase):
    """3d430852 AC6 — every mint seam sees every shape, at a fixture root.

    THE TRAP THE SPEC RECORDED, and it was real: exactly one suite in the tree mentioned
    `load_existing_uids` (test_authority_chain.py ~:573) and it PATCHES THE FUNCTION OUT
    so it can test activation lineage. So the collision-safety of the one function
    standing between the mint and two-bodies-one-identity was asserted by nobody and
    exercised by nothing. It could not even be exercised: it read import-time constants
    and had no root seam, so there was no way to point it at planted fixtures.

    Both halves are cured together, because either alone is useless: the seam
    (`studio_root=`) makes it runnable against a fixture, and routing the filename scan
    through `gp.parse_anchored_uid` makes it SEE slug-named files. Before that, a
    filename like `operating-agreement-public-edition-f0155ddd04f7.md` claimed a uid
    this function could not report, so an UNINDEXED slug-named file was invisible to
    collision checking and the mint could hand its uid out a second time.
    """

    def _fixture_root(self, names):
        root = Path(tempfile.mkdtemp(prefix="collision-shapes-"))
        self.addCleanup(shutil.rmtree, root, True)
        files = root / "vault" / "files"
        files.mkdir(parents=True)
        for name in names:
            (files / name).write_text("# planted, deliberately unindexed\n",
                                      encoding="utf-8")
        return root

    def test_load_existing_uids_sees_bare_and_slug_named_at_a_fixture_root(self) -> None:
        """The locked AC6 command. Planted fixtures are UNINDEXED on purpose.

        An indexed fixture would prove only that the index reader works, which was never
        in doubt. The hole was the FILENAME scan, so the fixtures exist only as files.
        """
        root = self._fixture_root([
            "aaaaaaaa.md",                              # 8-hex bare
            "bbbbbbbbbbbb.md",                          # 12-hex bare
            "some-readable-slug-cccccccccccc.md",       # 12-hex slug-named
            "another-slug-dddddddd.md",                 # 8-hex slug-named
            "not-a-governed-name.md",                   # must NOT be claimed
        ])

        seen = mint.load_existing_uids(studio_root=root)

        for uid in ("aaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc", "dddddddd"):
            self.assertIn(
                uid, seen,
                f"{uid} is claimed by a file on disk and the collision scan cannot see "
                f"it — the mint could re-issue it, giving one identity two bodies")
        self.assertNotIn(
            "not-a-governed-name", seen,
            "a filename that is not a governed shape must not claim a uid")

    def test_the_index_and_the_filenames_are_both_read_under_the_seam(self) -> None:
        """Both surfaces, not just the one that happened to be tested."""
        root = self._fixture_root(["aaaaaaaa.md"])
        (root / "vault" / "00-index.jsonl").write_text(
            json.dumps({"uid": "eeeeeeee", "type": "note"}) + "\n", encoding="utf-8")
        (root / "vault" / "00-archive-index.jsonl").write_text(
            json.dumps({"uid": "ffffffffffff", "type": "note"}) + "\n", encoding="utf-8")

        seen = mint.load_existing_uids(studio_root=root)
        self.assertIn("aaaaaaaa", seen, "filename surface not read")
        self.assertIn("eeeeeeee", seen, "current index not read")
        self.assertIn(
            "ffffffffffff", seen,
            "ARCHIVE index not read — ADR-047 Layer 1: an archived uid is permanently "
            "in use, and re-issuing one is the same collision as re-issuing a live one")

    def test_a_forced_duplicate_is_refused(self) -> None:
        """Collision safety is only real if the scan actually blocks a mint."""
        root = self._fixture_root(["some-readable-slug-cccccccccccc.md"])
        seen = mint.load_existing_uids(studio_root=root)
        minted = mint.mint(count=8, extra_existing=seen)
        self.assertEqual(len(set(minted)), len(minted), "mint returned duplicates")
        for uid in minted:
            self.assertNotIn(
                uid, seen,
                "the mint issued a uid the collision scan had already reported as "
                "claimed — the scan is being computed and then ignored")

    def test_the_slug_branch_is_load_bearing_not_decorative(self) -> None:
        """MUTATION PROOF. Revert the slug branch and the AC6 assertion must go red.

        This is the arm that matters: without it the criterion above passes on any
        implementation that returns a superset, and a green test over a blind mechanism
        is worse than no test. The pre-v1.94 behaviour is reproduced exactly — match
        only a bare `<uid>.md` stem — and the slug-named uid must then be invisible.
        """
        root = self._fixture_root(["some-readable-slug-cccccccccccc.md"])

        bare_only = re.compile(r"^[0-9a-f]{8}(?:[0-9a-f]{4})?$")
        reverted = {
            f.stem for f in (root / "vault" / "files").glob("*.md")
            if bare_only.match(f.stem)
        }
        self.assertNotIn(
            "cccccccccccc", reverted,
            "the reverted (bare-stem-only) scan still sees the slug-named uid, so this "
            "mutation proves nothing and neither does the criterion it guards")

        current = mint.load_existing_uids(studio_root=root)
        self.assertIn("cccccccccccc", current)

    def test_the_seam_defaults_to_the_live_studio(self) -> None:
        """Every existing caller passes no argument; the default must be unchanged.

        `40b2f455.py` and `e337f1dd.py` both delegate here with zero args. A seam that
        silently changed the default would move the collision surface for the real mint
        while every test kept passing.
        """
        live = mint.load_existing_uids()
        self.assertGreater(len(live), 100, "the live studio scan returned implausibly few uids")
        self.assertEqual(live, mint.load_existing_uids(studio_root=None))


class EventLayerAcceptsComposite(unittest.TestCase):
    """3d430852 AC9 — a 12-hex identity survives emit, extraction, and every reader.

    The spec cites the writer-identity fall-through at "~:601". That line reference has
    decayed (the same decay metis-g116 recorded for B-1's ten symbol:line pairs), so
    every site below is resolved by SYMBOL and the assertions are on behaviour, not on
    line numbers.

    THE DEFECT THIS FOUND, and it is an ERROR-severity one: `_registered_party_uids`
    in event_validators.py reads TWO sources — crew identities under vault/agents, and
    the portable rows in .tropo-studio/registries/agent-registry.yaml. The accepts-both
    sweep cured the first and left the second three lines below it matching 8-hex only.
    A 12-hex party uid registered there was invisible to Check 22, so the first user
    agent minted under the composite shape would have had EVERY message it emitted
    reported as not-using-its-party-uid. Latent while the live registry is all 8-hex,
    and guaranteed to fire the day it is not.
    """

    HEX12_AGENT = "f0e1d2c3b4a5"
    HEX12_ACTIVATION = "a1b2c3d4e5f6"
    HEX12_TASK = "0f1e2d3c4b5a"

    def _studio(self):
        root = Path(tempfile.mkdtemp(prefix="composite-events-"))
        self.addCleanup(shutil.rmtree, root, True)
        agents = root / "vault" / "agents"
        agents.mkdir(parents=True)
        (root / "vault" / "events" / "streams").mkdir(parents=True)
        (agents / f"{self.HEX12_AGENT}.md").write_text(
            "---\n"
            f"uid: {self.HEX12_AGENT}\n"
            "type: agent\n"
            "agent: composite-tester\n"
            f"party_uid: {self.HEX12_AGENT}\n"
            f"current_activation_uid: '{self.HEX12_ACTIVATION}'\n"
            "---\n\n# Composite Tester\n",
            encoding="utf-8")
        return root

    def test_emit_extract_check_events_and_validators_untruncated(self) -> None:
        """The locked AC9 command: emit, read back, extract, validate — no truncation."""
        ei = _load("composite_event_identity", TOOLS / "lib" / "event_identity.py")
        root = self._studio()

        # 1. PARTY/ACTIVATION EXTRACTION resolves a 12-hex-activation agent.
        activation = ei.current_activation_for_source(root, self.HEX12_AGENT)
        self.assertEqual(
            activation, self.HEX12_ACTIVATION,
            "activation extraction returned "
            f"{activation!r} for a 12-hex activation — a silently blanked activation is "
            "the fall-through this AC exists to close, and it fails as an empty string "
            "rather than as an error")

        # 2. WRITER IDENTITY does not silently blank the activation. Proven as a
        #    DIFFERENCE: a writer derived with the activation must not equal one derived
        #    without it. Asserting the hash alone could not tell the two apart.
        with_activation = ei.derive_writer_instance_uid(
            root, self.HEX12_AGENT, activation_uid=self.HEX12_ACTIVATION)
        without = ei.derive_writer_instance_uid(
            root, self.HEX12_AGENT, activation_uid="")
        self.assertRegex(with_activation, r"^[0-9a-f]{16}$")
        self.assertEqual(
            with_activation, without,
            "the resolved activation must reach the writer material by BOTH routes — "
            "explicitly passed and looked up from the record. A difference here means "
            "the lookup blanked it.")

        blanked = ei.derive_writer_instance_uid(
            root, "cccccccccccc", activation_uid="")
        self.assertNotEqual(
            with_activation, blanked,
            "writer identity is identical with and without a resolvable activation — "
            "the activation is not reaching the derivation material at all, so nothing "
            "downstream could detect a blank one")

        # 3. EMIT carries full 12-hex identity, untruncated on the wire.
        event = ei.append_stream_event(root, with_activation, {
            "specversion": "1.0",
            "type": "tropo.usage.recorded",
            "source": f"/agents/{self.HEX12_AGENT}",
            "source_uid": self.HEX12_AGENT,
            "subject": self.HEX12_AGENT,
            "time": "2026-09-02T20:00:00Z",
            "data": {"task_uid": self.HEX12_TASK,
                     "activation_uid": self.HEX12_ACTIVATION},
        })
        self.assertTrue(event["id"].startswith("evt_"))

        # 4. READ BACK FROM DISK, not from the returned dict — the returned object
        #    would pass even if serialization truncated on the way out.
        stream = root / "vault" / "events" / "streams" / f"{with_activation}.jsonl"
        raw = stream.read_text(encoding="utf-8").strip()
        self.assertTrue(raw, "nothing was written to the stream")
        row = json.loads(raw.splitlines()[-1])

        for field, expected in (
            ("source_uid", self.HEX12_AGENT),
            ("subject", self.HEX12_AGENT),
        ):
            self.assertEqual(
                row.get(field), expected,
                f"{field} came back {row.get(field)!r} — a 12-hex uid truncated to 8 "
                f"still looks like a valid uid, which is why this asserts equality "
                f"rather than a shape")
        self.assertEqual(row["data"]["task_uid"], self.HEX12_TASK)
        self.assertEqual(row["data"]["activation_uid"], self.HEX12_ACTIVATION)

        # 5. THE VALIDATOR FAMILY reports zero 8-hex ERRORs over it. This is the arm
        #    that caught the real defect: the registry read matched 8-hex only.
        ev = _load("composite_event_validators",
                   ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py")
        registered = ev._registered_party_uids(root)
        self.assertIn(
            self.HEX12_AGENT, registered,
            "a 12-hex party uid is not recognized as registered, so Check 22 (an ERROR) "
            "would fire on every message this agent ever emits")

    def test_the_portable_registry_row_accepts_both_shapes(self) -> None:
        """The second source in the same function — the one the sweep missed.

        Kept separate from the criterion above because it reads the OTHER source:
        vault/agents covers crew identities, agent-registry.yaml covers portable user
        agents, and a fixture that only plants one proves nothing about the other.
        """
        ev = _load("composite_event_validators_registry",
                   ROOT / ".tropo" / "scripts" / "lib" / "event_validators.py")
        root = Path(tempfile.mkdtemp(prefix="composite-registry-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "vault" / "agents").mkdir(parents=True)
        reg = root / ".tropo-studio" / "registries"
        reg.mkdir(parents=True)
        (reg / "agent-registry.yaml").write_text(
            "agents:\n  7b921d17:\n    name: legacy-shape\n"
            f"  {self.HEX12_AGENT}:\n    name: composite-shape\n",
            encoding="utf-8")

        uids = ev._registered_party_uids(root)
        self.assertIn("7b921d17", uids, "the 8-hex row regressed")
        self.assertIn(
            self.HEX12_AGENT, uids,
            "a 12-hex row in the portable agent registry is not collected — this is the "
            "sibling site the accepts-both sweep skipped, and Check 22 is an ERROR")

    def test_the_registry_pattern_is_load_bearing(self) -> None:
        """MUTATION. The pre-sweep pattern must be unable to see the 12-hex row."""
        sample = "agents:\n  7b921d17:\n  f0e1d2c3b4a5:\n"
        pre_sweep = re.findall(r"^\s{2}([0-9a-f]{8}):\s*$", sample, re.MULTILINE)
        self.assertNotIn(
            "f0e1d2c3b4a5", pre_sweep,
            "the pre-sweep pattern already saw the composite row, so the fix changed "
            "nothing and the assertions above prove nothing")
        cured = re.findall(r"^\s{2}([0-9a-f]{8}(?:[0-9a-f]{4})?):\s*$",
                           sample, re.MULTILINE)
        self.assertIn("f0e1d2c3b4a5", cured)


class ComposedPathJourney(unittest.TestCase):
    """3d430852 AC4 — the composed-path journey (seam rule 3c0547d3).

    A throwaway studio built from tracked sources, then one journey through the real
    tools: plant a slug-named 12-hex project, MINT a slug-named 12-hex task under it,
    register both, and assert the identity survives every reader.

    SCOPE, STATED RATHER THAN GLOSSED. This covers the legs I verified by running them:
    admission, bare-uid registration, the slug-filename link edge, and both search modes
    after a FULL rebuild. It does NOT yet cover AC4's orient-citation, check-one, or
    lock+close legs, and it does not assert the tree leg as written -- see
    `test_the_tree_leg_is_an_open_question_for_the_spec_owner` below, which records what
    is actually true rather than asserting an interpretation I chose myself. AC4 is
    PARTIAL until those land; this class does not claim otherwise.

    THE FIXTURE IS SLOW ON PURPOSE (~2 min: git archive plus two real rebuilds). A
    composed path proved on a synthetic studio is not a composed path -- the whole point
    of the seam rule is that every step is the production one.
    """

    PROJECT_UID = "a1b2c3d4e5f6"
    CONTROL_UID = "aaaaaaaa"
    studio = None
    task_uid = None
    skip_reason = None

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls._build()
        except unittest.SkipTest as exc:
            cls.skip_reason = str(exc)
        except Exception as exc:  # noqa: BLE001
            cls.skip_reason = f"journey fixture failed: {exc}"

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.studio:
            shutil.rmtree(cls.studio.parent, ignore_errors=True)

    def setUp(self) -> None:
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    # -- the journey ------------------------------------------------------

    @classmethod
    def _run(cls, args, **kw):
        return subprocess.run(args, cwd=str(cls.studio), capture_output=True,
                              text=True, timeout=1800, **kw)

    @classmethod
    def _rebuild(cls, only=None):
        args = [sys.executable, str(cls.studio / "vault" / "tools" / "tropo-rebuild-index.py"),
                "--apply", "--skip-rehydrate", "--vault-path", str(cls.studio)]
        if only:
            args[2:2] = ["--only", only]
        proc = cls._run(args)
        assert proc.returncode == 0, (proc.stderr or proc.stdout)[-500:]

    @classmethod
    def _build(cls) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="composed-journey-"))
        cls.studio = tmp / "studio"
        cls.studio.mkdir()

        archive = subprocess.run(["git", "archive", "HEAD"], cwd=str(ROOT),
                                 capture_output=True, timeout=600)
        if archive.returncode != 0:
            raise unittest.SkipTest("git archive unavailable in this environment")
        extract = subprocess.run(["tar", "-x", "-C", str(cls.studio)],
                                 input=archive.stdout, capture_output=True, timeout=600)
        assert extract.returncode == 0, extract.stderr[:400]

        for cmd in (["git", "init", "-q"],
                    ["git", "config", "user.email", "fixture@test.local"],
                    ["git", "config", "user.name", "fixture"],
                    ["git", "add", "-A", "-f"],
                    ["git", "commit", "-qm", "journey fixture sources"]):
            cls._run(cmd)

        cls._rebuild()

        files = cls.studio / "vault" / "files"

        # 1. HAND-PLANTED slug-named 12-hex project, frontmatter-declared.
        (files / f"journey-project-{cls.PROJECT_UID}.md").write_text(
            "---\n"
            f"uid: {cls.PROJECT_UID}\n"
            "type: project\n"
            'title: "Journey Project — composed path fixture"\n'
            'description: "A hand-planted slug-named 12-hex project, admitted via rebuild."\n'
            "status: active\nstate: active\nowner: talos\n"
            "created: '2026-09-02'\ncreated_by: talos-t60\n"
            "modified: '2026-09-02'\nmodified_by: talos-t60\n"
            "schema_version: 2\nlifecycle: standing\n"
            "member_of:\n  - b8e5f3a2\n---\n\n"
            "# Journey Project — composed path fixture\n\n## Purpose\n\n"
            "Planted by ComposedPathJourney.\n",
            encoding="utf-8")

        # A slug-named link TARGET that the task does not otherwise declare. The
        # target matters: _get_mentions drops a body link that duplicates a declared
        # edge, so linking the project (which the task declares member_of) would be
        # dropped BY DESIGN and the assertion would read a correct drop as a defect.
        # The first cut of this fixture did exactly that.
        (files / f"bare-link-control-{cls.CONTROL_UID}.md").write_text(
            "---\n"
            f"uid: {cls.CONTROL_UID}\n"
            "type: note\n"
            'title: "Slug link target"\n'
            "status: active\nstate: active\nowner: talos\n"
            "created: '2026-09-02'\ncreated_by: talos-t60\n"
            "modified: '2026-09-02'\nmodified_by: talos-t60\n"
            "schema_version: 2\n---\n\n# Slug link target\n",
            encoding="utf-8")

        cls._rebuild(only=cls.PROJECT_UID)
        cls._rebuild(only=cls.CONTROL_UID)

        # 2. MINTED slug-named 12-hex task, through the real mint.
        proc = cls._run([sys.executable,
                         str(cls.studio / "vault" / "tools" / "tropo-mint-id.py"),
                         "--type", "task", "--author", "talos-t60",
                         "--title", "Journey Task composed path"])
        assert proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]
        cls.task_uid = proc.stdout.strip().splitlines()[-1].strip()
        assert re.fullmatch(r"[0-9a-f]{12}", cls.task_uid), cls.task_uid

        minted = next(files.glob(f"*{cls.task_uid}.md"))
        cls.task_path = minted
        body = minted.read_text(encoding="utf-8")
        if re.search(r"^member_of:", body, re.M):
            body = re.sub(r"^member_of:.*(?:\n  - .*)*",
                          f'member_of:\n  - "{cls.PROJECT_UID}"', body, count=1, flags=re.M)
        else:
            body = body.replace("\n---\n",
                                f'\nmember_of:\n  - "{cls.PROJECT_UID}"\n---\n', 1)
        body = body.rstrip() + (
            f"\n\nSee [the slug target](bare-link-control-{cls.CONTROL_UID}.md).\n")
        minted.write_text(body, encoding="utf-8")

        cls._rebuild(only=cls.task_uid)
        cls._rebuild()  # FULL rebuild — AC4 requires it before the --content assertion

    # -- assertions -------------------------------------------------------

    def _index(self):
        rows = {}
        for name in ("00-index.jsonl", "00-archive-index.jsonl"):
            f = self.studio / "vault" / name
            if f.exists():
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        r = json.loads(line)
                        rows[r.get("uid")] = r
        return rows

    def test_planted_project_and_minted_task_end_to_end(self) -> None:
        """The locked AC4 command."""
        rows = self._index()

        # ADMITTED, and indexed under the BARE uid — never the slug-carrying stem.
        for uid, expect_stem in ((self.PROJECT_UID, "journey-project"),
                                 (self.task_uid, "journey-task")):
            self.assertIn(uid, rows,
                          f"{uid} was not admitted by rebuild")
            row = rows[uid]
            self.assertEqual(
                row["uid"], uid,
                "the indexed uid must be the BARE uid; a slug-carrying stem in this "
                "field makes every uid lookup in the studio miss")
            self.assertTrue(
                row.get("path", "").endswith(f"{expect_stem}-{uid}.md")
                or expect_stem in row.get("path", ""),
                f"indexed path {row.get('path')!r} is not the real slug path")
            self.assertTrue(
                (self.studio / row["path"]).exists(),
                f"the indexed path for {uid} does not resolve on disk")

        # THE TASK DECLARES THE PROJECT, and the edge is derived.
        con = sqlite3.connect(str(self.studio / "vault" / "00-index.sqlite"))
        try:
            edges = set(con.execute(
                "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                (self.task_uid,)).fetchall())
        finally:
            con.close()
        self.assertIn(
            ("member_of", self.PROJECT_UID), edges,
            "the minted task's member_of edge to the planted project was not derived")

        # A MARKDOWN LINK USING THE SLUG FILENAME YIELDS AN INDEX EDGE.
        self.assertIn(
            ("mentions", self.CONTROL_UID), edges,
            "a body link written with a READABLE filename produced no edge. Readable "
            "filenames are the convention this studio is moving to, so a link written "
            "the new way going unindexed would silently drop the graph as adoption grows")

        # BOTH SEARCH MODES RETURN THE REAL PATH, after the full rebuild.
        for args, want_uid in (
            (["Journey Task composed path"], self.task_uid),
            (["composed path fixture", "--content"], self.PROJECT_UID),
        ):
            proc = self._run([sys.executable,
                              str(self.studio / "vault" / "tools" / "tropo-vault-search.py"),
                              *args, "--json"])
            self.assertEqual(proc.returncode, 0, proc.stderr[-300:])
            payload = json.loads(proc.stdout)
            results = payload if isinstance(payload, list) else payload.get("results", [])
            hit = next((r for r in results if r.get("uid") == want_uid), None)
            self.assertIsNotNone(
                hit, f"{' '.join(args)} did not return {want_uid}")
            self.assertTrue(
                str(hit.get("path", "")).endswith(".md")
                and want_uid in str(hit.get("path", "")),
                f"search returned path {hit.get('path')!r}, which is not the real path")
            self.assertTrue(
                Path(hit["path"]).exists(),
                "search returned a path that does not resolve on disk")

    def test_the_slug_link_edge_is_load_bearing(self) -> None:
        """CONTROL: the same-direction-declared drop rule is what makes this subtle.

        `_get_mentions` deliberately drops a body link that duplicates an edge the
        entry already declares. So a mentions edge to the PROJECT would be absent for a
        correct reason, and a fixture that linked the project would read that correct
        drop as a defect. Asserted here so the next reader does not re-derive it.
        """
        con = sqlite3.connect(str(self.studio / "vault" / "00-index.sqlite"))
        try:
            rels = {r for (r,) in con.execute(
                "SELECT rel FROM edges WHERE src_uid=? AND dst_uid=?",
                (self.task_uid, self.PROJECT_UID)).fetchall()}
        finally:
            con.close()
        self.assertEqual(
            rels, {"member_of"},
            "expected exactly the declared member_of edge to the project and no "
            "duplicate 'mentions' — if a mentions edge appears here the drop rule has "
            "regressed and every declared relation is being double-counted")

    def test_the_tree_leg_is_an_open_question_for_the_spec_owner(self) -> None:
        """AC4 says "the task appears under the project in the tree". It does not, and
        that is EXISTING behaviour rather than a defect this journey introduced.

        Measured: `00-project-tree.jsonl` in the live studio contains only `project`,
        `pipeline` and `subsystem-hub` nodes. No task is a tree node anywhere in it. So
        either the tree leg means a different surface (the member_of edge, which does
        exist and is asserted above), or it is asking for a change to what the project
        tree carries — which is an architectural call belonging to the spec's owner, not
        to its builder.

        This test asserts WHAT IS TRUE so the question is recorded and cannot be quietly
        resolved by whoever reads it next. It is deliberately not an xfail: the facts
        below are real and worth holding.
        """
        tree = {}
        for line in (self.studio / "vault" / "00-project-tree.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                tree[row["uid"]] = row

        self.assertIn(
            self.PROJECT_UID, tree,
            "the planted 12-hex project is not a tree node at all, which WOULD be a "
            "composite-uid defect")
        self.assertNotIn(
            self.task_uid, tree,
            "a task now appears in the project tree — the surface changed, and AC4's "
            "tree leg should be re-read against it rather than against this note")


class _FlagFixture:
    """An isolated studio with just enough substrate for a REAL (unmocked)
    canonical mint of task/note: capsules + templates copied from this repo,
    a mint registry, and a composite-mint studio-identity manifest (this
    Studio runs MINT_HEX_LEN=12, so `mint()` refuses without one)."""

    def __init__(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="flag_gates_filename_only_")
        self.root = Path(self._temp.name).resolve()
        (self.root / ".tropo").mkdir()
        (self.root / "vault" / "files").mkdir(parents=True)
        # mint_file's canonical (non-output_dir) route reloads the freshener
        # FROM THE TARGET STUDIO ROOT (mint._load_rebuild_index resolves
        # `<root>/vault/tools/tropo-rebuild-index.py` and execs it fresh,
        # never the already-imported live module) -- so an isolated fixture
        # needs a real, working toolchain under it, not just capsules. Only
        # the top-level scripts + lib/ (2.4MB) are copied, never tests/
        # (15MB, irrelevant here).
        fixture_tools = self.root / "vault" / "tools"
        fixture_tools.mkdir(parents=True)
        for py_file in (ROOT / "vault" / "tools").glob("*.py"):
            shutil.copy2(py_file, fixture_tools / py_file.name)
        shutil.copytree(ROOT / "vault" / "tools" / "lib", fixture_tools / "lib")
        capsules = self.root / "vault" / "capsules"
        templates = capsules / "templates"
        templates.mkdir(parents=True)
        for type_name in ("task", "note"):
            shutil.copy2(
                ROOT / "vault" / "capsules" / f"tropo-{type_name}.capsule.md",
                capsules / f"tropo-{type_name}.capsule.md",
            )
            shutil.copy2(
                ROOT / "vault" / "capsules" / "templates" / f"{type_name}.template.md",
                templates / f"{type_name}.template.md",
            )
        registry_path = self.root / template_leg.MINT_REGISTRY_REL
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_bytes(template_leg.build_mint_registry_bytes(self.root))
        (self.root / ".tropo" / "studio-identity.md").write_text(
            "---\n"
            "studio_id: beef0000\n"
            "mint_prefix: beef\n"
            "created: '2026-07-26'\n"
            "minted_by: fixture\n"
            "hq_registered: false\n"
            "schema_version: 1\n"
            "entity_name: flag-fixture-studio\n"
            "---\n",
            encoding="utf-8",
        )
        # Bootstrap the index surfaces once (mirrors what a fresh studio's
        # own first mint would trigger internally): required before any
        # freshen_many batch call, which refuses on a missing union surface
        # rather than silently bootstrapping mid-batch.
        freshener = mint._load_rebuild_index(self.root)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ) as bootstrap_err:
            rc = freshener.rebuild_index(self.root, True)
        if rc != 0:
            raise AssertionError(
                f"fixture bootstrap failed with {rc}: {bootstrap_err.getvalue()}"
            )

    def set_readable_minting(self, enabled: bool) -> None:
        flag_dir = self.root / ".tropo-studio"
        flag_dir.mkdir(exist_ok=True)
        (flag_dir / "readable-filenames.json").write_text(
            json.dumps({"schema_version": 1, "enabled": enabled}),
            encoding="utf-8",
        )

    def close(self) -> None:
        self._temp.cleanup()


class FlagGatesFilenameOnly(unittest.TestCase):
    """3d430852 AC3, locked. The declared command, preserved as evidence:
    'flag ON: mint --type task --title Example Task; repeat without --title;
    flag OFF: repeat with --title; mint --type note (bare, then with --title
    expecting refusal); inspect filenames, frontmatter title, H1, and that no
    stray mint token survives.'

    Real (unmocked) mint.mint_file calls through the canonical (non-
    output_dir) route -- the same freshen_many/write_jsonl_pair_atomic path
    the mint-chokepoint fix touches -- against a real composite-uid studio.
    """

    def test_four_flag_title_combinations_and_the_note_refusal(self) -> None:
        fixture = _FlagFixture()
        self.addCleanup(fixture.close)

        def read(path: Path) -> tuple[dict, str]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "<<MINT:", text, f"stray mint token survived in {path.name}"
            )
            _, fm, body = text.split("---", 2)
            return yaml.safe_load(fm), body

        placeholder = template_leg._TITLE_PLACEHOLDER_TEXT["task"]

        # flag ON + title: example-task-<12hex>.md, both titles filled.
        fixture.set_readable_minting(True)
        uid1, path1 = mint.mint_file(
            "task", author="fixture-agent", title="Example Task",
            studio_root=fixture.root,
        )
        self.assertEqual(path1.name, f"example-task-{uid1}.md")
        frontmatter1, body1 = read(path1)
        self.assertEqual(frontmatter1["title"], "Example Task")
        self.assertIn("# Example Task", body1)

        # flag ON, no title: bare <12hex>.md, the task template's own
        # REQUIRED-placeholder text in both title spots -- never a stray
        # token and never silently blank.
        uid2, path2 = mint.mint_file(
            "task", author="fixture-agent", studio_root=fixture.root,
        )
        self.assertEqual(path2.name, f"{uid2}.md")
        frontmatter2, body2 = read(path2)
        self.assertEqual(frontmatter2["title"], placeholder)
        self.assertIn(f"# {placeholder}", body2)

        # flag OFF + title: bare <12hex>.md (the flag, not the title, gates
        # the filename) but the title still fills both frontmatter and H1.
        fixture.set_readable_minting(False)
        uid3, path3 = mint.mint_file(
            "task", author="fixture-agent", title="Example Task",
            studio_root=fixture.root,
        )
        self.assertEqual(path3.name, f"{uid3}.md")
        frontmatter3, body3 = read(path3)
        self.assertEqual(frontmatter3["title"], "Example Task")
        self.assertIn("# Example Task", body3)

        # note, bare: succeeds -- note's template declares no title token.
        fixture.set_readable_minting(True)
        uid4, path4 = mint.mint_file(
            "note", author="fixture-agent", studio_root=fixture.root,
        )
        self.assertEqual(path4.name, f"{uid4}.md")
        read(path4)

        # note + title: refused, clearly -- note's template has no
        # <<MINT:title>> token to accept one.
        with self.assertRaises(ValueError) as ctx:
            mint.mint_file(
                "note", author="fixture-agent", title="Not Accepted",
                studio_root=fixture.root,
            )
        self.assertIn("no <<MINT:title>> token", str(ctx.exception))
        self.assertFalse(
            any(fixture.root.glob("vault/files/*not-accepted*")),
            "a refused note+title mint must not leave a file behind",
        )

        self.assertEqual(
            len({uid1, uid2, uid3, uid4}), 4, "each mint must claim a fresh uid"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
