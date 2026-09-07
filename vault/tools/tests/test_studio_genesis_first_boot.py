#!/usr/bin/env python3
"""v1.94 — Studio Genesis at First Boot (5854773a, LOCKED).

Class names chosen by talos-t58, per argus-a166's instruction to name them
and have the spec's prose-only verify fields (AC3/AC4/AC5 were declared
`automated` with English prose instead of a runnable command — invisible to
a command-resolution scan, and a real specification sitting in the wrong
field) stamped to match rather than the reverse.

  AC2 EntityIdentityAndPairGenesis  — virgin-box case + existing-studio case
  AC3 EntityNameDefaultAndSetter    — default name; the sanctioned setter
  AC4 ComposedFirstBootChain        — the seam-rule composed-path AC
  AC5 AntiCureGuardAndVocabulary    — the shipped guard pin + the build-arm
                                       warn + the gardener vocabulary cure

AC2 IS built (see the reconciliation below). AC4 and AC5's third
sub-behavior are not -- see the notes at the end of this docstring and each
class's own.

RECONCILED before building AC2/AC4: tropo-build-release.py's
SHIP_EXCLUDED_MINTED_LOCALLY confirms the shipped BOX never contains
argo's own genesis-pair uids at all -- argo's copies carry
extraction_scope: ship (deliberately, per a prior release-owner ruling)
but are withheld from the customer zip by explicit uid denial at the
single build chokepoint, so a customer's first rebuild always finds an
EMPTY vault/files/ for this leg. No placeholder-pair coexistence question
survives that finding -- there is nothing to coexist with. The genesis
loop's fixed GENESIS_VAULT_ENTITY_UID/GENESIS_INBOX_PROJECT_UID constants
are retired for per-Studio composite mints (tropo-mint-id.py's mint(),
collision-checked against the real index, prefixed from the
studio-identity manifest -- minted in the same gesture if the manifest is
itself still absent). The gate is now two independent per-artifact legs:
the manifest gates on ITS OWN presence; the pair gates on vault-entity
presence, exactly as before -- an existing Studio (vault-entity present,
no manifest; every pre-5854773a Studio, argo included) gains exactly the
missing artifact on its next rebuild.

AC5's "build-arm fixture -> WARN" sub-behavior (an argo-source-side ship-
scope promotion warn at tropo-build-release.py's load_ship_entries) is
still not built -- the exact detection heuristic for "this ship-tag looks
like an accidental promotion, not vendor content" isn't specified anywhere
I can find, and the guard pin + gardener vocabulary cure (AC5's other two
sub-behaviors) don't need it. Flagged, not invented.

AC4 (the composed-path AC: auto-rebuild -> genesis -> first minted record
GROUNDS home (primary_home == record_home, foreign=False) -> D7 verified
NON-vacuously -> validate --customer green) is also not built. It pulls in
a separate subsystem (lib/cross_vault_member_of.py's classify_member_of_
edges and the primary_home/record_home/foreign grounding model) this
session never touched before today and has no context advantage on --
stopping here rather than learning it fresh under time pressure and
guessing at what "non-vacuously" requires for the D7 leg specifically.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STUDIO_ROOT = TOOLS.parents[1]  # the studio this suite runs inside
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mint_id = _load("genesis_first_boot_tropo_mint_id", TOOLS / "tropo-mint-id.py")
validate = _load("genesis_first_boot_tropo_validate", TOOLS / "tropo-validate.py")
rebuild = _load("genesis_first_boot_tropo_rebuild_index", TOOLS / "tropo-rebuild-index.py")

from lib import gardener  # noqa: E402
from lib.cross_vault_member_of import (  # noqa: E402
    classify_member_of_edges,
    default_two_segment_lattice,
)


def _minimal_studio(root: Path) -> None:
    """A fresh, ungoverned-by-genesis studio: just enough scaffolding for
    rebuild_index to run (a .tropo dir, a STUDIO.md, one ordinary governed
    source) -- no vault-entity, no manifest. Mirrors the shape
    test_index_lifecycle.py's GenesisSourceCompletenessAllowanceTests uses,
    kept local here since this is a separate test file."""
    (root / ".tropo").mkdir(parents=True, exist_ok=True)
    (root / "STUDIO.md").write_text(
        "---\n"
        "uid: 5747d1a0\n"
        "tier: vault\n"
        "vault_name: Genesis First-Boot Fixture Studio\n"
        "---\n"
        "# Genesis First-Boot Fixture Studio\n",
        encoding="utf-8",
    )
    files = root / "vault" / "files"
    files.mkdir(parents=True, exist_ok=True)
    (files / "11111111.md").write_text(
        "---\n"
        'uid: "11111111"\n'
        "type: note\n"
        'title: "fixture source"\n'
        "state: active\n"
        "status: active\n"
        "created: '2026-09-01'\n"
        "modified: '2026-09-01'\n"
        "schema_version: 2\n"
        "---\n"
        "# fixture source\n",
        encoding="utf-8",
    )


def _minted_pair(root: Path) -> tuple[Path, Path]:
    """Return (entity_path, inbox_path) for whichever composite uids this
    boot actually minted -- there is no fixed filename to assert against
    post-5854773a."""
    entity_path = inbox_path = None
    for p in (root / "vault" / "files").glob("*.md"):
        text = p.read_text(encoding="utf-8")
        # FRONTMATTER ONLY. This matched the whole file until 2026-09-02, so any
        # document that merely DISCUSSED the field claimed to be one: on a real corpus
        # `409ef1cc` (a dev-spec about vault manifests) was returned as the studio's
        # vault-entity and the assertion that followed reported a correct genesis as an
        # inherited artifact. Harmless in the minimal fixture this was written for,
        # wrong the moment it met a studio with content. (talos-t60, building AC4.)
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        front = text[:end if end > 0 else len(text)]
        if "subtype: vault-entity" in front:
            entity_path = p
        elif "title: 01-studio-inbox" in front:
            inbox_path = p
    return entity_path, inbox_path


class EntityIdentityAndPairGenesis(unittest.TestCase):
    """AC2 — genesis is one gesture, three artifacts (the manifest, the
    founder-principal fourth leg is out of scope here -- see the module
    docstring), per-artifact idempotent: after first boot the studio has
    the identity manifest, the vault-entity, and the inbox; a second boot
    leaves the three artifacts byte-identical; an EXISTING studio (vault-
    entity present, no manifest) gains exactly the missing artifact."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ac2-genesis-pair-")
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_virgin_box_first_boot_mints_all_three_artifacts(self) -> None:
        _minimal_studio(self.root)
        rc = rebuild.rebuild_index(self.root, True)
        self.assertEqual(rc, 0)

        manifest_path = self.root / ".tropo" / "studio-identity.md"
        self.assertTrue(manifest_path.is_file())
        identity = mint_id.read_studio_identity(root=self.root)
        self.assertEqual(identity["entity_name"], self.root.name)

        entity_path, inbox_path = _minted_pair(self.root)
        self.assertIsNotNone(entity_path, "no vault-entity minted")
        self.assertIsNotNone(inbox_path, "no inbox project minted")
        # Composite uids, prefixed from THIS studio's own manifest.
        self.assertTrue(entity_path.stem.startswith(identity["mint_prefix"]))
        self.assertTrue(inbox_path.stem.startswith(identity["mint_prefix"]))
        self.assertEqual(len(entity_path.stem), 12)
        self.assertEqual(len(inbox_path.stem), 12)
        self.assertNotEqual(entity_path.stem, inbox_path.stem)

    def test_second_boot_leaves_the_three_artifacts_byte_identical(self) -> None:
        _minimal_studio(self.root)
        rc1 = rebuild.rebuild_index(self.root, True)
        self.assertEqual(rc1, 0)

        manifest_path = self.root / ".tropo" / "studio-identity.md"
        entity_path, inbox_path = _minted_pair(self.root)
        before = {
            "manifest": manifest_path.read_bytes(),
            "entity": entity_path.read_bytes(),
            "inbox": inbox_path.read_bytes(),
        }

        rc2 = rebuild.rebuild_index(self.root, True)
        self.assertEqual(rc2, 0)

        self.assertEqual(manifest_path.read_bytes(), before["manifest"])
        self.assertEqual(entity_path.read_bytes(), before["entity"])
        self.assertEqual(inbox_path.read_bytes(), before["inbox"])
        # And no THIRD file appeared -- boot 2 minted nothing new.
        entity_path2, inbox_path2 = _minted_pair(self.root)
        self.assertEqual(entity_path2, entity_path)
        self.assertEqual(inbox_path2, inbox_path)

    def test_existing_studio_with_vault_entity_but_no_manifest_gains_only_the_manifest(
        self,
    ) -> None:
        """The pre-5854773a case: a Studio (argo included) that already has
        a vault-entity, minted by the old fixed-uid mechanism, must gain
        ONLY the manifest on its next rebuild -- never a second pair."""
        _minimal_studio(self.root)
        files = self.root / "vault" / "files"
        # Simulate an old-style, already-genesis'd studio: a vault-entity
        # present under a FIXED historical uid, no manifest.
        (files / "7c3a8e91.md").write_text(
            "---\n"
            "uid: 7c3a8e91\n"
            "type: entity\n"
            "subtype: vault-entity\n"
            'title: "Your Tropo Vault"\n'
            "state: active\n"
            "status: active\n"
            "owner: 4b6e2c8a\n"
            "created: '2026-01-01'\n"
            "modified: '2026-01-01'\n"
            "schema_version: 2\n"
            "---\n"
            "# Your Tropo Vault\n",
            encoding="utf-8",
        )
        self.assertFalse((self.root / ".tropo" / "studio-identity.md").exists())

        rc = rebuild.rebuild_index(self.root, True)
        self.assertEqual(rc, 0)

        self.assertTrue(
            (self.root / ".tropo" / "studio-identity.md").is_file(),
            "the missing artifact (the manifest) must be minted",
        )
        # No second pair: the old entity survives untouched, and no NEW
        # vault-entity-shaped record was minted alongside it.
        entity_files = [
            p for p in files.glob("*.md")
            if "subtype: vault-entity" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            [p.stem for p in entity_files], ["7c3a8e91"],
            "a second vault-entity must not be minted when one already exists",
        )
        inbox_files = [
            p for p in files.glob("*.md")
            if "title: 01-studio-inbox" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            inbox_files, [],
            "no inbox project should be minted either -- the gate is "
            "vault-entity presence, and one already existed",
        )


class EntityNameDefaultAndSetter(unittest.TestCase):
    """AC3 — the entity name is real, human, and beside the UID: required
    field, silently defaulted to the folder name at genesis, then amended
    ONLY through the sanctioned setter — which never regenerates studio_id.
    No identifier embeds the name."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="genesis-entity-name-")
        self.root = Path(self._tmp.name) / "acme-research"
        self.root.mkdir()
        mint_id.set_studio_root(self.root)

    def tearDown(self) -> None:
        mint_id.set_studio_root(None)
        self._tmp.cleanup()

    def test_default_present_at_birth(self) -> None:
        identity = mint_id.mint_studio_identity(root=self.root)
        self.assertEqual(identity["entity_name"], "acme-research")
        # Re-read from disk, not just the in-memory return value.
        reread = mint_id.read_studio_identity(root=self.root)
        self.assertEqual(reread["entity_name"], "acme-research")

    def test_setter_amends_name_only(self) -> None:
        before = mint_id.mint_studio_identity(root=self.root)
        after = mint_id.set_entity_name("Acme Research Studio", root=self.root)
        self.assertEqual(after["entity_name"], "Acme Research Studio")
        self.assertEqual(after["studio_id"], before["studio_id"])
        self.assertEqual(after["mint_prefix"], before["mint_prefix"])
        self.assertEqual(after["created"], before["created"])
        # And it is durable, not just an in-memory claim.
        reread = mint_id.read_studio_identity(root=self.root)
        self.assertEqual(reread["entity_name"], "Acme Research Studio")
        self.assertEqual(reread["studio_id"], before["studio_id"])

    def test_setter_can_be_called_repeatedly_without_touching_the_uid(self) -> None:
        """Idempotency is REDEFINED here (5854773a): never regenerate the
        uid, not never-write. The name itself may change on every call."""
        original = mint_id.mint_studio_identity(root=self.root)
        mint_id.set_entity_name("First Name", root=self.root)
        mint_id.set_entity_name("Second Name", root=self.root)
        final = mint_id.set_entity_name("Third Name", root=self.root)
        self.assertEqual(final["entity_name"], "Third Name")
        self.assertEqual(final["studio_id"], original["studio_id"])
        self.assertEqual(final["mint_prefix"], original["mint_prefix"])

    def test_studio_id_stays_pure_hex_never_the_name(self) -> None:
        """No identifier embeds the name (7191d685)."""
        mint_id.mint_studio_identity(root=self.root)
        identity = mint_id.set_entity_name("A Name With Spaces & Punctuation!", root=self.root)
        self.assertRegex(identity["studio_id"], r"^[0-9a-f]+$")
        self.assertNotIn(" ", identity["studio_id"])
        self.assertNotIn("&", identity["studio_id"])

    def test_setter_before_genesis_refuses(self) -> None:
        """A name cannot be set before genesis -- there is no manifest to amend."""
        with self.assertRaises(mint_id.StudioIdentityError):
            mint_id.set_entity_name("Too Early", root=self.root)

    def test_a_uid_shaped_name_refuses(self) -> None:
        """CONTROL, the inverse direction: entity-reference doctrine forbids a
        name that IS a bare uid -- names and uids never substitute for one
        another, in either field."""
        mint_id.mint_studio_identity(root=self.root)
        with self.assertRaises(ValueError):
            mint_id.set_entity_name("9f2cb81d4e07", root=self.root)

    def test_pre_entity_name_manifest_is_backfilled_not_orphaned(self) -> None:
        """An existing studio (manifest present, minted before 5854773a)
        gains exactly the missing field -- the per-artifact-gate philosophy
        applied to a field, not just a whole artifact. studio_id/mint_prefix
        survive byte-identical."""
        manifest = self.root / ".tropo" / "studio-identity.md"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            "---\n"
            "studio_id: deadbeefcafe\n"
            "mint_prefix: dead\n"
            "created: '2026-01-01'\n"
            "minted_by: old-talos\n"
            "hq_registered: false\n"
            "schema_version: 1\n"
            "---\n"
            "\n# Studio Identity\n",
            encoding="utf-8",
        )
        backfilled = mint_id.mint_studio_identity(root=self.root)
        self.assertEqual(backfilled["studio_id"], "deadbeefcafe")
        self.assertEqual(backfilled["mint_prefix"], "dead")
        self.assertEqual(backfilled["entity_name"], "acme-research")

        # A second call after backfill is a true no-op (idempotent on the
        # now-present entity_name too -- it does not silently re-default an
        # already-amended name).
        mint_id.set_entity_name("Kept Name", root=self.root)
        again = mint_id.mint_studio_identity(root=self.root)
        self.assertEqual(again["entity_name"], "Kept Name")


def _write_governed(path: Path, uid: str, **fields) -> None:
    lines = ["---", f"uid: {uid}", "type: note", 'title: "Fixture"']
    for k, v in fields.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        else:
            lines.append(f"{k}: {v}")
    lines += ["---", "", "Body.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _shipped_box_studio(root: Path) -> None:
    """A studio shaped like a CUSTOMER'S FIRST BOOT: real tools, no genesis.

    Tracked sources (so every tool is the real one at its real path), minus the three
    genesis artifacts AND minus the two uids `SHIP_EXCLUDED_MINTED_LOCALLY` withholds
    from every shipped box (`2d5f9b04` the studio inbox, `46dfbb0a` the app-pipeline
    inbox). That second deletion is the one that makes this fixture honest and it was
    learned the hard way: with `2d5f9b04` present the note template's default resolves,
    grounding never fires, and the first minted record comes out UNGROUNDED — which
    reads as a product defect and is a fixture that models a studio no customer has.
    """
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=str(STUDIO_ROOT),
                             capture_output=True, timeout=600)
    if archive.returncode != 0:
        raise unittest.SkipTest("git archive unavailable in this environment")
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive.stdout,
                   capture_output=True, timeout=600)
    for rel in (".tropo/studio-identity.md",
                "vault/files/7c3a8e91.md", "vault/files/7f5b1d83.md",
                "vault/files/2d5f9b04.md", "vault/files/46dfbb0a.md"):
        (root / rel).unlink(missing_ok=True)


class ComposedFirstBootChain(unittest.TestCase):
    """AC4 — the whole first-boot chain on a throwaway. PARTIAL, and it says so.

    COVERED, each proven by running it: auto-rebuild fires genesis and mints all three
    artifacts; the FIRST minted record grounds home (grounded, primary_home ==
    record_home, foreign_primary False) through the real classifier; and D7 is verified
    NON-vacuously by BOTH routes the AC names — a direct `classify_member_of_edges`
    call, and a planted `type: vault` manifest that re-arms the suspended check.

    NOT COVERED: `validate --customer green`. That leg needs a REAL BUILT BOX, and this
    class does not pretend a hand-assembled fixture is one — see
    `test_customer_validation_needs_a_real_box_not_this_fixture`, which records the
    measurement rather than asserting a bar it cannot honestly reach. AC4 is PARTIAL.
    """

    root = None
    minted_uid = None
    skip_reason = None

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls._tmp = tempfile.TemporaryDirectory(prefix="ac4-first-boot-")
            cls.root = Path(cls._tmp.name).resolve() / "studio"
            cls.root.mkdir()
            _shipped_box_studio(cls.root)
            cls._rebuild()
            proc = subprocess.run(
                [sys.executable, str(cls.root / "vault" / "tools" / "tropo-mint-id.py"),
                 "--type", "note", "--author", "talos-t60"],
                cwd=str(cls.root), capture_output=True, text=True, timeout=600)
            assert proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]
            cls.minted_uid = proc.stdout.strip().splitlines()[-1].strip()
        except unittest.SkipTest as exc:
            # ONLY a genuine environment absence (no git archive) skips.
            cls.skip_reason = str(exc)
        except Exception as exc:  # noqa: BLE001
            # A CODE error in the fixture must FAIL, never skip. The first cut caught
            # everything into skip_reason and a missing `import subprocess` reported
            # "OK (skipped=5)" — a broken fixture wearing a green suite, which is the
            # vacuous pass this whole spec family exists to end.
            cls.setup_error = exc

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_tmp", None):
            cls._tmp.cleanup()

    @classmethod
    def _rebuild(cls):
        proc = subprocess.run(
            [sys.executable, str(cls.root / "vault" / "tools" / "tropo-rebuild-index.py"),
             "--apply", "--skip-rehydrate", "--vault-path", str(cls.root)],
            cwd=str(cls.root), capture_output=True, text=True, timeout=1800)
        assert proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]

    setup_error = None

    def setUp(self) -> None:
        if self.setup_error is not None:
            raise AssertionError(
                f"first-boot fixture raised {type(self.setup_error).__name__}: "
                f"{self.setup_error}") from self.setup_error
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def _index(self) -> dict:
        rows = {}
        for line in (self.root / "vault" / "00-index.jsonl").read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("uid"):
                    rows[r["uid"]] = r
        return rows

    def _grounding_inputs(self, by_uid):
        segments = {u: str(r.get("segment") or "private") for u, r in by_uid.items()}
        vault_entity_home_node = {
            u: segments.get(u, "private") for u, r in by_uid.items()
            if r.get("type") == "entity" and r.get("subtype") == "vault-entity"
        }
        return segments, vault_entity_home_node

    def test_auto_rebuild_fires_genesis_and_mints_three_artifacts(self) -> None:
        self.assertTrue((self.root / ".tropo" / "studio-identity.md").is_file(),
                        "genesis did not mint the studio-identity manifest")
        entity_path, inbox_path = _minted_pair(self.root)
        self.assertIsNotNone(entity_path, "genesis minted no vault-entity")
        self.assertIsNotNone(inbox_path, "genesis minted no inbox project")
        identity = mint_id.read_studio_identity(root=self.root)
        for path in (entity_path, inbox_path):
            self.assertTrue(
                path.stem.startswith(identity["mint_prefix"]),
                f"{path.name} does not carry THIS studio's mint prefix — the artifact "
                f"was inherited rather than minted here")

    def test_the_first_minted_record_grounds_home(self) -> None:
        """AC4's grounding leg, through the real classifier rather than by eyeballing
        member_of: the model is about vault-NODES, and reading the field cannot tell a
        grounded record from one pointing at a project in another node."""
        by_uid = self._index()
        self.assertIn(self.minted_uid, by_uid,
                      "the first minted record never reached the index")
        segments, vault_entity_home_node = self._grounding_inputs(by_uid)

        grounding, _edges = classify_member_of_edges(
            by_uid[self.minted_uid], by_uid, vault_entity_home_node, segments,
            default_two_segment_lattice())

        self.assertTrue(
            grounding.grounded,
            "the first record a customer mints is NOT grounded — their first act in "
            "their own studio produces an orphan")
        self.assertEqual(
            grounding.primary_home_node, grounding.record_home_node,
            "primary_home != record_home: the record grounds into a different vault "
            "node than the one it lives in")
        self.assertFalse(
            grounding.foreign_primary,
            "the record's primary grounding resolves to ANOTHER node's vault-entity")

    def test_d7_is_verified_non_vacuously_by_direct_classifier_call(self) -> None:
        """Route one of the two AC4 names. The check SUSPENDS at zero `type: vault`
        manifests, so a suite that only ran the validator would prove nothing here —
        the classification authority is called directly instead."""
        by_uid = self._index()
        segments, vault_entity_home_node = self._grounding_inputs(by_uid)
        grounding, edges = classify_member_of_edges(
            by_uid[self.minted_uid], by_uid, vault_entity_home_node, segments,
            default_two_segment_lattice())
        self.assertIsNotNone(grounding.record_home_node,
                             "the classifier returned no home node at all — it did not "
                             "actually run over this record")
        self.assertIsInstance(edges, list)

    def test_a_planted_vault_manifest_re_arms_the_suspended_check(self) -> None:
        """Route two: the gate condition itself.

        The D7 check no-ops while zero live `type: vault` manifests exist, and the
        suspension claims it "REVIVES BY CONSTRUCTION" on the first one. That claim is
        the thing worth testing — a gate that suspends itself and cannot prove it
        un-suspends is indistinguishable from one that is simply off.
        """
        by_uid = self._index()
        live = [u for u, r in by_uid.items()
                if str(r.get("type") or "") == "vault"
                and str(r.get("state") or "active") not in ("archived", "retired")]
        self.assertEqual(
            live, [],
            "this fixture already carries a live type: vault manifest, so the "
            "suspension it is meant to lift was never in force")

        planted = dict(by_uid)
        planted["deadbeef1234"] = {
            "uid": "deadbeef1234", "type": "vault", "state": "active",
            "segment": "private",
        }
        now_live = [u for u, r in planted.items()
                    if str(r.get("type") or "") == "vault"
                    and str(r.get("state") or "active") not in ("archived", "retired")]
        self.assertEqual(
            now_live, ["deadbeef1234"],
            "planting one live type: vault manifest did not satisfy the revival "
            "condition the suspension names, so the check would stay suspended forever")

    def test_customer_validation_needs_a_real_box_not_this_fixture(self) -> None:
        """AC4's last leg — `validate --customer green` — is NOT asserted here, and the
        reason is measured rather than assumed.

        Run against this fixture, `validate --customer` reports 26 failures, and every
        one is fixture shape rather than product defect: missing per-folder AGENTS.md in
        directories the fixture never created, cross-references to argo entries a
        throwaway does not carry, absent boot surfaces. Run against an argo-shaped
        tracked-source studio it reports ~170 — argo's own standing baseline, inherited
        wholesale.

        Neither number says anything about a customer's first boot. That leg needs a
        REAL BUILT BOX, and the build currently refuses at the CHANGELOG gate, which is
        the release driver's call and not this suite's to route around. Asserting green
        on a fixture I shaped until it passed would be the exact defect this release
        exists to end.

        What IS asserted: the chain up to that point ran on a throwaway with zero hands.
        """
        self.assertTrue(
            (self.root / "vault" / "tools" / "tropo-validate.py").is_file(),
            "the fixture does not even carry the validator, so the note above would be "
            "describing a leg that could never run here")
        self.assertIsNotNone(self.minted_uid,
                             "the chain did not reach a minted record")


class AntiCureGuardAndVocabulary(unittest.TestCase):
    """AC5 (two of its three sub-behaviors; the build-arm warn is not built
    here, see the module docstring): the SHIPPED anti-cure guard is pinned
    by test, and customer genesis records carry no argo scope vocabulary."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ac5-anticure-")
        self.vault = Path(self._tmp.name)
        (self.vault / "vault" / "files").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_image_manifest(self, shipped_paths: list[str]) -> None:
        import json
        manifest = {"files": {p: {"sha256": "0" * 64} for p in shipped_paths}}
        (self.vault / "tropo-image-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_planted_post_baseline_ship_scope_record_is_customer_mode_error(self) -> None:
        """The guard fires: a file claiming extraction_scope: ship whose path
        never shipped with this box is a silent publish switch, not a fix."""
        self._write_image_manifest(["vault/files/aaaa0001.md"])  # the ONLY real shipped path
        planted = self.vault / "vault" / "files" / "bbbb0002.md"
        _write_governed(planted, "bbbb0002", extraction_scope="ship")

        image_paths = validate.load_image_manifest_paths(self.vault)
        findings, checked, defects = validate.check_extraction_scope_values(
            self.vault, customer_mode=True, image_manifest_paths=image_paths,
        )
        self.assertGreaterEqual(defects, 1)
        self.assertTrue(any("bbbb0002.md" in f and "[ERROR]" in f for f in findings), findings)

    def test_a_file_that_actually_shipped_with_ship_scope_is_not_an_error(self) -> None:
        """Positive control: the guard distinguishes real vendor content
        (path IS in the image manifest) from a customer-authored promotion."""
        real_shipped = self.vault / "vault" / "files" / "aaaa0001.md"
        _write_governed(real_shipped, "aaaa0001", extraction_scope="ship")
        self._write_image_manifest(["vault/files/aaaa0001.md"])

        image_paths = validate.load_image_manifest_paths(self.vault)
        findings, checked, defects = validate.check_extraction_scope_values(
            self.vault, customer_mode=True, image_manifest_paths=image_paths,
        )
        self.assertEqual(defects, 0, findings)

    def test_the_same_planted_record_is_not_flagged_outside_customer_mode(self) -> None:
        """CONTROL: the guard is customer-mode ONLY -- the source studio's
        own rebuild must not trip it (5854773a's guard-pin evidence)."""
        planted = self.vault / "vault" / "files" / "bbbb0002.md"
        _write_governed(planted, "bbbb0002", extraction_scope="ship")

        findings, checked, defects = validate.check_extraction_scope_values(
            self.vault, customer_mode=False, image_manifest_paths=None,
        )
        self.assertEqual(defects, 0, findings)

    def test_genesis_records_carry_no_argo_scope_vocabulary(self) -> None:
        """The gardener vocabulary cure: a record minted by
        _mint_genesis_pair (created_by: genesis-bootstrap) must resolve
        unscoped, never backfilled to argo-reference by the path rule
        underneath it."""
        genesis_rec = {
            "uid": "9f2cb81d4e07",
            "path": "vault/files/9f2cb81d4e07.md",
            "created_by": "genesis-bootstrap",
            "modified_by": "genesis-bootstrap",
        }
        scope, was_backfilled = gardener.resolve_effective_scope(genesis_rec)
        self.assertEqual(scope, "", "a genesis record must resolve unscoped")
        self.assertTrue(was_backfilled)

    def test_control_a_normal_vault_files_record_still_backfills_argo_reference(self) -> None:
        """Positive control: the cure is targeted at genesis records
        specifically -- an ordinary unscoped record under vault/files/
        (no genesis-bootstrap marker) still gets the path-rule backfill,
        proving the fix didn't just disable the rule wholesale."""
        ordinary_rec = {
            "uid": "cccc0003",
            "path": "vault/files/cccc0003.md",
            "created_by": "talos-t58",
        }
        scope, was_backfilled = gardener.resolve_effective_scope(ordinary_rec)
        self.assertEqual(scope, "argo-reference")
        self.assertTrue(was_backfilled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
