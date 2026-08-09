#!/usr/bin/env python3
"""Contract-first plants for ``vault/tools/tropo-folder.py``.

WHY THIS FILE IS RED TODAY
--------------------------
``vault/tools/tropo-folder.py`` does not exist. That is the point, and the red
directly beneath this docstring is the correct end state until the build lane
lands the tool. This crew has repeatedly lost days to a suite written *against*
an implementation: the tests pass, the behaviour is wrong, and green is what
stops anyone looking. Every case below was cut from
``vault/tools/FOLDER-MOUNT-SURFACE.md`` (frozen by Talos T37) and from the
checkpoint "the composition model" (``5e6652ac``) **before** the build, in a
lane that never sees the implementation. Nothing here is stubbed, mocked or
weakened to manufacture green. Do not create the module to clear the import.

THE CONTRACT SURFACE THESE PLANTS PIN (FOLDER-MOUNT-SURFACE.md, frozen)
-----------------------------------------------------------------------
::

    MOUNT_REGISTRY_REL = ".tropo-studio/folder-mounts.json"
    STATE_ATTACHED = "attached"   # agents have hands on it. No metadata.
    STATE_ADOPTED  = "adopted"    # the same mount, tooled.
    STATES = (STATE_ATTACHED, STATE_ADOPTED)

    @dataclass(frozen=True)
    class FolderMount:
        mount_uid / name / path / state / availability / mounted_at /
        mounted_by / adopted_at / fingerprint

    mount(root, path, *, name) -> FolderMount
    adopt(root, mount_uid)     -> AdoptReport
    reconcile(root, mount_uid=None) -> ReconcileReport
    mounts(root) -> list[FolderMount]
    main(argv=None) -> int

WHAT IS BEING BUILT, AND WHAT THE EXISTING MACHINERY REFUSES
-------------------------------------------------------------
The target is a OneDrive or SharePoint sync folder: no manifest, not a git
repo, sitting anywhere on the machine. ``tropo-mount.py`` mounts *vaults* and
requires all three of those things, so it refuses the primary use case by
design. ``tropo-import-walker.py`` has the adoption machinery — ``scan`` /
``create-sidecar`` / ``reconcile`` / ``ingest`` — but ``create-sidecar`` hard-
refuses a source outside the studio root ("Source file is not inside Studio
root") and ``ingest`` joins its scan root *under* the studio. Those two
refusals are the blockers this build removes, and ``ImportWalkerPriorArtTests``
pins that they are still there, so that a case here cannot quietly become a
statement about a tool somebody already changed.

THE CASES THAT CARRY THE WEIGHT
-------------------------------
* **One mount, two states** (``OneMountTwoStatesTests``). The checkpoint is
  explicit: *"These should be the same mount with a switch, not two features."*
  ``adopt`` mutates the existing record and the ``mount_uid`` survives. A suite
  that lets ``adopt`` mint a fresh uid has missed the entire design, so the
  uid-preservation case is paired with ``test_two_folders_get_two_different_
  uids`` — without that pair, an implementation that returns one constant uid
  forever would satisfy "the uid survived".
* **Attach requires nothing** (``AttachRequiresNothingTests``). One bare
  directory, one file, no git, no manifest, outside the studio tree, and the
  folder is byte-identical afterwards — not "unchanged apart from a marker".
  A mount that demands setup is the friction this build removes.
* **Sidecars canonical, projections derived** (``SidecarCanonicalTests``).
  TROPO-CONTROL invariant 8 is directional, so the sharp case is the one where
  the two disagree: a projection that contradicts its sidecar must lose.
* **Source files are never modified** (``SourceBytesTests``). Every source file
  is hashed before and after every operation, and adoption is allowed to add
  paths under ``<folder>/.tropo-studio/`` and nowhere else.
* **Imported bodies must not reach a model** (``EgressTests``). Outside origin
  is marked three independent ways and any one is enough. Eligibility is NOT
  re-derived from ``extraction_scope`` — that is a publishing label, and
  answering an egress question with it is a mistake this Studio has made three
  times. These cases call the shipped classifier in ``tropo-orient.py``
  (``egress_class`` / ``_imported``) rather than restating its rules, because a
  second copy of a policy is a second policy waiting to disagree.
* **Drift** (``DriftTests``) — the case with no prior art. A cloud folder
  re-syncs, its path changes, and nothing in this tree reconciles a mount
  against a moved folder today. The property: a moved folder is re-found and
  its ``mount_uid`` is preserved. A move must never look like an unmount plus a
  new mount.

THE ASYMMETRY, WHICH IS THE BUG THIS BUILD IS MOST LIKELY TO LEAVE BEHIND
--------------------------------------------------------------------------
Sidecars find their file by relative path (``../<name>``), so they survive a
whole-folder move for free and everything *looks* fine. Vault projections store
studio-relative ``source_path`` / ``original_path`` strings and break. That
asymmetry exists for in-tree moves today.
``test_reconcile_repairs_the_projection_handles_that_a_move_breaks`` pins the
fixed behaviour, and it is deliberately the most heavily controlled case in
this file: it refuses to run unless it can first prove the projection is
genuinely stale, because a plant that never reaches the broken state is exactly
how a green case ends up with a live mutant behind it.

THE SEARCH BOUND THIS FILE ASSUMES, STATED SO IT CAN BE ARGUED WITH
--------------------------------------------------------------------
``fingerprint`` has to answer "is this the same folder somewhere else?" without
the path, and the surface leaves the mechanism to the build lane. So the drift
fixtures move a folder the way a re-sync actually moves one: the leaf keeps its
name and the *parent* is renamed beside itself, e.g.
``<tmp>/sync/OneDrive - Acme/Marketing`` -> ``<tmp>/sync/OneDrive - Acme (1)/
Marketing``. The moved folder is therefore inside the same grandparent as
before. A re-finder that gives up before the grandparent of the path it
recorded cannot re-find a re-synced cloud folder, so that bound is the contract
these cases read. Nothing here asserts *how* the folder is re-found.

DISCIPLINE
----------
Hermetic. Nothing writes to the live studio: fixtures are built in ``tempfile``,
the one piece of real substrate a case needs is *copied out*, and a fingerprint
guard re-checks ``vault/files/``, ``recycle/`` and the absence of a live mount
registry after every single test — because the realistic way this tool damages
this studio is by resolving its own root from ``__file__`` while pointed at a
fixture. Module setup and teardown additionally compare ``git status
--porcelain``. No network: a process-wide socket guard, the sibling-suite
idiom. Every control that exists to prove a fixture did not silently no-op
reports through :meth:`FolderCase.assertPlanted`, which fails with a distinct
``FIXTURE DID NOT PLANT`` prefix so a broken plant can never be misread as a
contract failure.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from unittest import mock

try:  # optional; the line parser below covers everything these fixtures emit
    import yaml
except Exception:  # pragma: no cover - environment dependent
    yaml = None

TESTS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = TESTS_DIR.parent
LIVE_STUDIO = TOOLS_DIR.parent.parent

IMPORT_WALKER = TOOLS_DIR / "tropo-import-walker.py"
ORIENT_TOOL = TOOLS_DIR / "tropo-orient.py"
REBUILD_TOOL = TOOLS_DIR / "tropo-rebuild-index.py"

# The build under contract. Absent today. TROPO_FOLDER_PATH is the mutation
# seam and exists for one reason: proving this suite can fail means pointing it
# at a deliberately broken implementation in /tmp and reporting which cases
# caught what. CI sets nothing and gets vault/tools/tropo-folder.py.
FOLDER_TOOL_PATH = Path(
    os.environ.get("TROPO_FOLDER_PATH") or (TOOLS_DIR / "tropo-folder.py")
).resolve()


def _load_by_path(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_module_under_contract():
    """Load the hyphenated tool by path — the house idiom for vault/tools/*.py.

    Raises rather than skipping when the module is absent. A contract suite
    that skips itself into green is the failure mode this file exists to
    prevent, and an absent module is the loudest possible statement that the
    build has not landed yet.
    """
    if not FOLDER_TOOL_PATH.is_file():
        raise ModuleNotFoundError(
            f"the module under contract does not exist yet: {FOLDER_TOOL_PATH}. "
            "This suite was cut from FOLDER-MOUNT-SURFACE.md + checkpoint "
            "5e6652ac before the build, on purpose. Red here is the correct "
            "state until the folder-mount tool lands; do NOT stub the module "
            "to clear it."
        )
    return _load_by_path("tropo_folder_under_contract", FOLDER_TOOL_PATH)


folder = _load_module_under_contract()
rebuild_index = _load_by_path(
    "tropo_rebuild_index_for_folder_contract",
    REBUILD_TOOL,
)

# The shipped egress classifier. Real, loaded from the live tools dir, and
# never reimplemented here: EgressTests point orient's FILES at a fixture and
# ask IT the question. If this import breaks, the egress cases fail loudly
# rather than skipping — an egress case that skips is worse than no egress case.
try:
    orient = _load_by_path("tropo_orient_for_folder_contract", ORIENT_TOOL)
    _ORIENT_ERROR = None
except Exception as exc:  # pragma: no cover - environment dependent
    orient = None
    _ORIENT_ERROR = exc


# --------------------------------------------------------------------------- #
# Process-wide network guard — the sibling-suite idiom (test_tropo_smoke).     #
# Mounting a folder on this machine is a local operation end to end. Anything  #
# here that reaches for a socket is doing something nobody asked for.          #
# --------------------------------------------------------------------------- #
_SOCKET_PATCHERS = (
    mock.patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
    mock.patch.object(
        socket.socket,
        "connect_ex",
        side_effect=AssertionError("network forbidden by process-wide test guard"),
    ),
)


# --------------------------------------------------------------------------- #
# Live-studio guard.                                                            #
# --------------------------------------------------------------------------- #

def live_fingerprint() -> tuple:
    """Everything in this studio a folder-mount tool could plausibly damage."""

    def stamp(root: Path):
        if not root.exists():
            return ()
        return tuple(
            (p.relative_to(LIVE_STUDIO).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*"))
            if p.is_file()
        )

    return (
        stamp(LIVE_STUDIO / "vault" / "files"),
        stamp(LIVE_STUDIO / "recycle"),
        # The live studio has no folder mounts and this suite must not give it
        # one. `mounts()` and `list` are reads; a read that creates its own
        # registry is a write nobody asked for.
        (LIVE_STUDIO / ".tropo-studio" / "folder-mounts.json").exists(),
    )


_LIVE_AT_START: tuple = ()
_LIVE_GIT_AT_START: str = ""


def setUpModule():
    global _LIVE_AT_START, _LIVE_GIT_AT_START
    for patcher in _SOCKET_PATCHERS:
        patcher.start()
    _LIVE_AT_START = live_fingerprint()
    _LIVE_GIT_AT_START = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(LIVE_STUDIO),
        capture_output=True,
        text=True,
    ).stdout


def tearDownModule():
    for patcher in reversed(_SOCKET_PATCHERS):
        patcher.stop()
    after_git = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(LIVE_STUDIO),
        capture_output=True,
        text=True,
    ).stdout
    if after_git != _LIVE_GIT_AT_START:
        raise AssertionError(
            "this suite changed the LIVE studio's git state. Every call must "
            "resolve its paths from the root argument it was handed, never "
            f"from the tool's own location.\nbefore:\n{_LIVE_GIT_AT_START}\n"
            f"after:\n{after_git}"
        )


# --------------------------------------------------------------------------- #
# Fixture builders and readers                                                  #
# --------------------------------------------------------------------------- #

SIDECAR_DIR = ".tropo-studio"

# One real governed entry, copied out rather than authored: agent-written,
# `extraction_scope: ship`, none of the three import marks. It is the anti-case
# for the mistake this Studio keeps making, and a hand-rolled imitation of it
# would prove nothing about the real classifier's behaviour on real substrate.
REAL_ELIGIBLE_ENTRY = "0aefe71d"  # Deletion Discipline — Substrate Preservation


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path, *, skip_dirs: tuple = ()) -> dict:
    """Every file under ``root`` as ``relpath -> (sha256, size)``.

    Directories named in ``skip_dirs`` are pruned. This is what "byte-identical
    afterwards" is measured with, so it deliberately reports *paths* as well as
    contents: a tool that leaves a zero-byte marker behind has still written to
    a folder it promised not to touch.
    """
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            out[path.relative_to(root).as_posix()] = (sha256_of(path), path.stat().st_size)
    return out


def frontmatter(path: Path) -> dict:
    """The YAML frontmatter of a sidecar or projection, as a flat dict."""
    text = path.read_text(errors="ignore")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end] if end > 0 else text[3:]
    if yaml is not None:
        try:
            data = yaml.safe_load(block)
            if isinstance(data, dict):
                # Scalars come back as strings, matching the line parser below.
                # YAML resolves `source_hash: 000...0` to the INTEGER zero, and
                # a case that compares a hash to a hash must not depend on
                # which of the two parsers ran.
                parsed = {
                    key: value if value is None or isinstance(value, (dict, list)) else str(value)
                    for key, value in data.items()
                }
                # Unquoted 8-hex UIDs containing `e` can be interpreted by
                # PyYAML as scientific notation (even infinity). The shipped
                # stdlib parser treats identity fields as strings.
                uid_match = re.search(r"^uid:\s*([0-9a-f]{8})\s*$", block, re.MULTILINE)
                if uid_match:
                    parsed["uid"] = uid_match.group(1)
                return parsed
        except Exception:
            pass
    out = {}
    for line in block.splitlines():
        if not line.strip() or line[:1] in (" ", "\t", "#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value[:1] == '"' and value[-1:] == '"':
            try:
                value = json.loads(value)
            except Exception:
                value = value[1:-1]
        out[key.strip()] = value
    return out


def frontmatter_block(path: Path) -> str:
    text = path.read_text(errors="ignore")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end > 0 else text[3:]


def resolve_recorded(value, *, studio_root: Path, projection_dir: Path, mount_path: Path):
    """Resolve a recorded path string the way any consumer of it would.

    A projection's ``source_path`` is a string, and the surface does not fix
    which base it is relative to — studio-relative today, plausibly absolute
    for an out-of-tree mount tomorrow. So every base a reasonable consumer
    would try is tried, and only if *none* of them reaches a file is the handle
    called broken. That generosity is deliberate: this helper decides whether a
    drift case reddens, and it must redden for a stale handle rather than for a
    base it did not think of.
    """
    if not value or not isinstance(value, str):
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [
        studio_root / raw,
        mount_path / raw,
        mount_path.parent / raw,
        projection_dir / raw,
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


class FolderCase(unittest.TestCase):
    """One temp studio + one temp cloud folder per case, and a live guard."""

    def setUp(self) -> None:
        self._live_before = live_fingerprint()
        self._tmp = Path(tempfile.mkdtemp(prefix="tropo-folder-contract-")).resolve()
        self.addCleanup(shutil.rmtree, self._tmp, True)

    def tearDown(self) -> None:
        self.assertEqual(
            self._live_before,
            live_fingerprint(),
            msg="the tool wrote into the LIVE studio. Every path must be "
            "resolved from the `root` argument, never from the tool's own "
            "__file__ — a fixture-pointed call that reaches this checkout is "
            "the one realistic way this build damages the vault.",
        )

    # -- controls ---------------------------------------------------------- #
    def assertPlanted(self, condition, message: str) -> None:
        """A control on the FIXTURE, not on the tool.

        Every case that plants a state asserts it reached that state before it
        asserts anything about behaviour. A plant that silently no-ops is how a
        case goes green with its mutant alive, which has happened here five
        times this week; the distinct prefix means a control failure can never
        be read as a contract failure.
        """
        if not condition:
            raise AssertionError(f"FIXTURE DID NOT PLANT: {message}")

    # -- fixtures ---------------------------------------------------------- #
    def studio(self, name: str = "studio") -> Path:
        """A minimal but real-shaped studio: a vault, an index, a .tropo-studio.

        Deliberately NOT a git repo and deliberately carrying no vault
        manifest. If any of this tool's operations turns out to need one, that
        need shows up here as a failure rather than being hidden by a fixture
        that was over-built to keep the suite quiet.
        """
        root = self._tmp / name
        (root / "vault" / "files").mkdir(parents=True, exist_ok=True)
        (root / ".tropo-studio").mkdir(parents=True, exist_ok=True)
        index = root / "vault" / "00-index.jsonl"
        if not index.exists():
            index.write_text("", encoding="utf-8")
        studio_md = root / "STUDIO.md"
        if not studio_md.exists():
            studio_md.write_text("# fixture studio\n", encoding="utf-8")
        return root

    def cloud_folder(self, *, parent: str = "sync/OneDrive - Acme",
                     leaf: str = "Marketing", files=None) -> Path:
        """A folder the way the primary use case delivers one.

        Outside the studio tree, no manifest, not a git repo, ordinary files
        with ordinary names. The default carries a nested file as well, because
        a real sync folder has subfolders and "nothing changed" has to hold at
        depth too.
        """
        path = self._tmp / parent / leaf
        path.mkdir(parents=True, exist_ok=True)
        payload = files if files is not None else {
            "quarterly-plan.md": "# Q3 plan\n\nShip the thing.\n",
            "notes.txt": "call notes 2026-07-30\n",
            "assets/logo-brief.md": "# logo brief\n\nblue, not that blue\n",
        }
        for rel, body in payload.items():
            target = path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        return path

    def source_digest(self, folder_path: Path) -> dict:
        return tree_digest(folder_path, skip_dirs=(SIDECAR_DIR,))

    # -- helpers ----------------------------------------------------------- #
    def only_mount(self, root: Path):
        records = folder.mounts(root)
        self.assertEqual(
            len(records), 1,
            msg=f"expected exactly one mount record, got {len(records)}: "
                f"{[getattr(m, 'mount_uid', m) for m in records]}",
        )
        return records[0]

    def assertMountUid(self, value) -> None:
        self.assertIsInstance(value, str)
        self.assertRegex(
            value, r"^[0-9a-f]{8}$",
            msg="the frozen surface says mount_uid is 8-hex, minted once",
        )

    def sidecars_in(self, folder_path: Path) -> list:
        return sorted(folder_path.rglob(f"{SIDECAR_DIR}/*.tropo.md"))

    def projections_in(self, root: Path) -> list:
        return sorted((root / "vault" / "files").glob("*.md"))

    def assertSourcesUnchanged(self, folder_path: Path, before: dict, when: str) -> None:
        after = self.source_digest(folder_path)
        self.assertEqual(
            before, after,
            msg=f"a source file changed during {when}. Source files are never "
                "modified — publishing back stays additive through "
                "tropo-export.py's `stem v-NN` scheme, which never overwrites.",
        )


# --------------------------------------------------------------------------- #
# The frozen names                                                              #
# --------------------------------------------------------------------------- #

class SurfaceTests(FolderCase):
    """The names both lanes build to. Neither lane invents one."""

    def test_the_registry_lives_at_the_frozen_relative_path(self) -> None:
        """The registry path is a studio-relative constant, and it is shared.

        Two lanes and a future reconciler all have to find the same file. A
        registry that moved to `.tropo/` or into the mounted folder itself
        would be invisible to everything written against this constant.
        """
        self.assertEqual(folder.MOUNT_REGISTRY_REL, ".tropo-studio/folder-mounts.json")

    def test_the_two_states_are_the_frozen_strings_and_there_is_no_third(self) -> None:
        """One feature with a switch means the switch has exactly two positions.

        A third state is how "one mount, two states" quietly becomes three
        kinds of thing, which is the design error the checkpoint is written
        against.
        """
        self.assertEqual(folder.STATE_ATTACHED, "attached")
        self.assertEqual(folder.STATE_ADOPTED, "adopted")
        self.assertEqual(tuple(folder.STATES), ("attached", "adopted"))

    def test_foldermount_is_frozen_and_carries_the_nine_named_fields(self) -> None:
        """A record handed to callers is a value, not a handle they can edit.

        `frozen=True` is in the surface for a reason: the registry file is the
        writable surface, and a mutable record invites a caller to change a
        mount's state in memory and never persist it — the exact way a
        `mount_uid` gets lost.
        """
        self.assertTrue(is_dataclass(folder.FolderMount))
        names = [f.name for f in dataclass_fields(folder.FolderMount)]
        self.assertEqual(
            names,
            ["mount_uid", "name", "path", "state", "availability",
             "mounted_at", "mounted_by", "adopted_at", "fingerprint"],
        )
        self.assertTrue(
            getattr(folder.FolderMount, "__dataclass_params__").frozen,
            msg="the surface declares @dataclass(frozen=True)",
        )

    def test_the_five_entry_points_and_two_report_types_exist(self) -> None:
        """Import-level proof that the surface was built to, before behaviour.

        A missing name here produces one clear failure instead of twenty
        confusing ones downstream.
        """
        for name in ("mount", "adopt", "reconcile", "mounts", "main"):
            self.assertTrue(callable(getattr(folder, name, None)), msg=f"missing {name}()")
        for name in ("AdoptReport", "ReconcileReport"):
            self.assertTrue(hasattr(folder, name), msg=f"missing {name} (named in the surface)")

    def test_mount_takes_name_as_a_keyword_only_argument(self) -> None:
        """`mount(root, path, *, name)`, so a caller cannot swap path and name.

        Two adjacent strings in positional order is a defect waiting for a
        hurried call site; the surface froze the keyword and this is the cheap
        way to keep it.
        """
        import inspect

        signature = inspect.signature(folder.mount)
        parameter = signature.parameters.get("name")
        self.assertIsNotNone(parameter, msg="mount() has no `name` parameter")
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_uid_shaped_scalars_are_never_parsed_as_scientific_notation(self):
        self.assertEqual(folder.walker._parse_yaml("uid: 114e8351")["uid"], "114e8351")


# --------------------------------------------------------------------------- #
# Attach requires nothing                                                       #
# --------------------------------------------------------------------------- #

class AttachRequiresNothingTests(FolderCase):
    """Day one. No manifest, no git, no clean tree, no write into the folder."""

    def test_attach_works_on_a_bare_directory_with_one_file(self) -> None:
        """The floor case, stated as plainly as the checkpoint states it.

        "This is how a marketing SharePoint folder becomes useful on day one."
        One directory, one file, nothing else. Anything the tool needs beyond
        that is friction this build exists to remove, and it fails here.
        """
        root = self.studio()
        bare = self.cloud_folder(files={"one-file.md": "hello\n"})
        self.assertPlanted(
            sorted(p.name for p in bare.iterdir()) == ["one-file.md"],
            "the bare folder was supposed to contain exactly one file",
        )
        self.assertPlanted(not (bare / ".git").exists(), "the bare folder must not be a git repo")

        record = folder.mount(root, bare, name="Marketing")

        self.assertMountUid(record.mount_uid)
        self.assertEqual(record.state, folder.STATE_ATTACHED)
        self.assertEqual(record.name, "Marketing")
        self.assertEqual(Path(record.path).resolve(), bare.resolve())
        self.assertTrue(str(record.mounted_by or "").strip(), msg="every action carries a name")
        datetime.fromisoformat(str(record.mounted_at).replace("Z", "+00:00"))

    def test_attach_leaves_the_folder_byte_identical(self) -> None:
        """Not "unchanged apart from a marker". Byte-identical, paths included.

        A marker file written at attach would be the easy way to solve drift,
        and it is barred: attach must require nothing and write nothing, so the
        re-finder has to work on an untouched folder. This is also the case
        that keeps a mount from being a modification of somebody's OneDrive.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        before = tree_digest(cloud)
        self.assertPlanted(
            len(before) >= 3 and "quarterly-plan.md" in before,
            f"the fixture folder should hold the seeded files; saw {sorted(before)}",
        )

        folder.mount(root, cloud, name="Marketing")

        after = tree_digest(cloud)
        self.assertEqual(
            before, after,
            msg="attach wrote into the mounted folder. Attach requires nothing "
                "and writes nothing: no marker, no manifest, no dotfile.",
        )

    def test_attach_accepts_a_folder_outside_the_studio_root(self) -> None:
        """The blocker this build removes, stated as a passing requirement.

        `tropo-import-walker.py create-sidecar` raises "Source file is not
        inside Studio root" and `ingest` joins its root under the studio. The
        checkpoint names this as the single gap blocking the stated use case:
        Mike's own files, which must live in SharePoint for work reasons.
        """
        root = self.studio()
        outside = self.cloud_folder(parent="elsewhere/OneDrive - Acme", leaf="Personal")
        with self.assertRaises(ValueError, msg="fixture is not actually outside the studio"):
            outside.relative_to(root)

        record = folder.mount(root, outside, name="Personal")

        self.assertEqual(record.state, folder.STATE_ATTACHED)
        self.assertEqual(Path(record.path).resolve(), outside.resolve())
        self.assertEqual([m.mount_uid for m in folder.mounts(root)], [record.mount_uid])

    def test_attach_accepts_a_dirty_git_repository(self) -> None:
        """No clean tree. `tropo-mount.py` refuses one; this must not.

        Vault mounting pins a commit into `compose.lock` and so refuses a dirty
        tree on purpose. A sync folder that happens to be a git checkout with
        uncommitted work is an ordinary folder, and reusing the vault gate here
        would mean gutting it.
        """
        root = self.studio()
        cloud = self.cloud_folder(leaf="Repo")
        subprocess.run(["git", "init", "-q"], cwd=str(cloud), check=True,
                       capture_output=True)
        (cloud / "uncommitted.md").write_text("dirty\n", encoding="utf-8")
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(cloud),
            capture_output=True, text=True,
        ).stdout
        self.assertPlanted(porcelain.strip(), "the fixture repo was supposed to be dirty")

        record = folder.mount(root, cloud, name="Repo")

        self.assertEqual(record.state, folder.STATE_ATTACHED)

    def test_attach_records_the_mount_in_the_studio_not_in_the_folder(self) -> None:
        """The registry belongs to the studio; the folder stays somebody else's.

        Paired with the byte-identity case: this one proves the record landed
        somewhere, so "the folder is untouched" cannot be satisfied by a mount
        that recorded nothing at all.
        """
        root = self.studio()
        cloud = self.cloud_folder()

        record = folder.mount(root, cloud, name="Marketing")

        registry = root / folder.MOUNT_REGISTRY_REL
        self.assertTrue(registry.is_file(), msg=f"no registry at {folder.MOUNT_REGISTRY_REL}")
        self.assertIn(record.mount_uid, registry.read_text(encoding="utf-8"))
        self.assertFalse(
            (cloud / SIDECAR_DIR).exists(),
            msg="attach created a .tropo-studio inside the mounted folder; "
                "adoption is what earns that directory, not attachment",
        )

    def test_an_attached_mount_has_no_adopted_at(self) -> None:
        """`adopted_at: Optional[str]` is the switch's off position on disk.

        A mount that is born with an adoption timestamp cannot be told apart
        from one that was adopted, which is the distinction the whole record
        exists to carry.
        """
        root = self.studio()
        cloud = self.cloud_folder()

        record = folder.mount(root, cloud, name="Marketing")

        self.assertIsNone(record.adopted_at)
        self.assertIsNone(self.only_mount(root).adopted_at)

    def test_attach_writes_no_sidecar_and_no_governed_entry(self) -> None:
        """"No metadata, no governance, no identifiers" — the checkpoint's words.

        ATTACHED is the state that must cost nothing. An implementation that
        quietly projects governed entries at attach has collapsed the two
        states back into one, from the other direction.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        before = self.projections_in(root)
        self.assertPlanted(before == [], "the fixture vault should start empty")

        folder.mount(root, cloud, name="Marketing")

        self.assertEqual(self.sidecars_in(cloud), [])
        self.assertEqual(self.projections_in(root), [])


# --------------------------------------------------------------------------- #
# One mount, two states                                                         #
# --------------------------------------------------------------------------- #

class OneMountTwoStatesTests(FolderCase):
    """The centre of the design. `adopt` flips a switch; it does not mint."""

    def attached(self, *, leaf: str = "Marketing"):
        root = self.studio()
        cloud = self.cloud_folder(leaf=leaf)
        record = folder.mount(root, cloud, name=leaf)
        self.assertPlanted(
            [m.mount_uid for m in folder.mounts(root)] == [record.mount_uid],
            "the fixture should hold exactly one attached mount before adopt",
        )
        self.assertPlanted(
            self.only_mount(root).state == folder.STATE_ATTACHED,
            "the fixture mount should be ATTACHED before adopt",
        )
        return root, cloud, record

    def test_adopt_preserves_the_mount_uid(self) -> None:
        """The single most important line in the surface.

        "ATTACHED and ADOPTED are one mount with a switch — not two kinds of
        thing. `adopt` mutates the existing record; it never creates a second
        one, and the `mount_uid` survives." Every governed entry that will ever
        point at this folder points at that uid; re-minting it on adoption
        orphans all of them at once, silently, on the happy path.

        The control is what makes this a case about adoption rather than about
        a function that returns without doing anything: adoption must have
        actually happened — the state flipped and sidecars exist — before the
        surviving uid means anything.
        """
        root, cloud, before = self.attached()

        folder.adopt(root, before.mount_uid)

        after = self.only_mount(root)
        self.assertPlanted(
            after.state == folder.STATE_ADOPTED and self.sidecars_in(cloud),
            "adopt did not adopt: no state flip and no sidecars, so a "
            "surviving mount_uid would prove nothing",
        )
        self.assertEqual(
            after.mount_uid, before.mount_uid,
            msg="adopt minted a new mount_uid. The uid is minted once and "
                "NEVER re-minted — a fresh one here turns one mount into two "
                "kinds of thing and orphans every governed entry pointing at "
                "the old uid.",
        )

    def test_adopt_never_creates_a_second_record(self) -> None:
        """The other half of the same sentence, read off the registry itself.

        Counting through `mounts()` alone would miss an implementation that
        appends a second record and de-duplicates on read; the raw registry is
        checked too, because the file is what the next process loads.
        """
        root, cloud, before = self.attached()
        registry = root / folder.MOUNT_REGISTRY_REL

        folder.adopt(root, before.mount_uid)

        records = folder.mounts(root)
        self.assertEqual(
            len(records), 1,
            msg=f"adopt turned one mount into {len(records)}. It flips a "
                "switch on the record that is already there.",
        )
        raw = registry.read_text(encoding="utf-8")
        self.assertEqual(
            raw.count(before.mount_uid), 1,
            msg="the mount_uid appears a number of times other than once in "
                "the registry; a second record was appended, or the original "
                "was replaced, even if mounts() hides it",
        )

    def test_adopt_flips_only_the_switch_and_keeps_every_identity_field(self) -> None:
        """Mutating the record means mutating it, not replacing it.

        `name`, `path`, `mounted_at` and `mounted_by` are the mount's identity
        and its provenance — who authorised it and when. A replacement record
        that re-stamps `mounted_at` to now has thrown away the only evidence
        of when this folder actually entered the studio.
        """
        root, _cloud, before = self.attached()

        folder.adopt(root, before.mount_uid)

        after = self.only_mount(root)
        self.assertEqual(after.name, before.name)
        self.assertEqual(Path(after.path).resolve(), Path(before.path).resolve())
        self.assertEqual(after.mounted_at, before.mounted_at)
        self.assertEqual(after.mounted_by, before.mounted_by)
        self.assertEqual(after.state, folder.STATE_ADOPTED)
        self.assertIsNotNone(
            after.adopted_at,
            msg="the switch flipped but nothing recorded when — adopted_at is "
                "the field that says this mount is tooled",
        )

    def test_two_folders_get_two_different_uids(self) -> None:
        """The pair that gives uid-preservation its teeth.

        Without this, an implementation that returns one constant uid forever
        satisfies "the mount_uid survived adoption" perfectly. Minting is only
        meaningful if it discriminates.
        """
        root = self.studio()
        first = folder.mount(root, self.cloud_folder(leaf="Marketing"), name="Marketing")
        second = folder.mount(root, self.cloud_folder(leaf="Finance"), name="Finance")

        self.assertMountUid(first.mount_uid)
        self.assertMountUid(second.mount_uid)
        self.assertNotEqual(
            first.mount_uid, second.mount_uid,
            msg="two distinct folders were given the same mount_uid",
        )
        self.assertEqual(len(folder.mounts(root)), 2)

    def test_adopting_twice_is_idempotent_down_to_the_uids(self) -> None:
        """Re-running a gesture is how a human recovers from a half-run.

        The import walker's `ingest` is idempotent for exactly this reason. A
        second `adopt` that appends a record, or re-mints, turns a retry into
        data loss — and the uids are where that loss actually lands, so this
        compares them rather than the file names. Re-minting per-file uids
        leaves the same sidecars at the same paths and orphans every governed
        entry that pointed at the old ones, which is the same failure the
        `mount_uid` case is about, one layer down.
        """
        root, cloud, before = self.attached()
        folder.adopt(root, before.mount_uid)
        first_pass = self.only_mount(root)
        sidecars = {p.relative_to(cloud).as_posix(): frontmatter(p).get("uid")
                    for p in self.sidecars_in(cloud)}
        projections = sorted(p.stem for p in self.projections_in(root))
        self.assertPlanted(sidecars, "the first adopt should have written sidecars")
        self.assertPlanted(all(sidecars.values()), f"a sidecar carries no uid: {sidecars}")

        folder.adopt(root, before.mount_uid)

        second_pass = self.only_mount(root)
        self.assertEqual(second_pass.mount_uid, before.mount_uid)
        self.assertEqual(second_pass.adopted_at, first_pass.adopted_at)
        self.assertEqual(len(folder.mounts(root)), 1)
        self.assertEqual(
            {p.relative_to(cloud).as_posix(): frontmatter(p).get("uid")
             for p in self.sidecars_in(cloud)},
            sidecars,
            msg="the second adopt changed the sidecars — a different set of "
                "files, or the same files with freshly minted uids. Re-running "
                "a gesture must not duplicate or re-identify the substrate it "
                "already made.",
        )
        self.assertEqual(
            sorted(p.stem for p in self.projections_in(root)), projections,
            msg="the second adopt left a different set of governed entries "
                "behind; the first pass's entries were orphaned",
        )

    def test_adopt_on_an_unknown_uid_never_mints_a_mount(self) -> None:
        """A typo at the CLI must not create a folder mount out of nothing.

        The surface does not say whether this raises or returns, so neither
        does this case — what it pins is that the registry cannot grow a record
        for a uid nobody mounted.
        """
        root, _cloud, before = self.attached()

        try:
            folder.adopt(root, "deadbeef")
        except Exception:
            pass

        self.assertEqual(
            [m.mount_uid for m in folder.mounts(root)], [before.mount_uid],
            msg="adopting an unknown uid changed the registry",
        )


# --------------------------------------------------------------------------- #
# Sidecars canonical, projections derived                                       #
# --------------------------------------------------------------------------- #

class SidecarCanonicalTests(FolderCase):
    """TROPO-CONTROL invariant 8, which is directional: the sidecar wins."""

    def adopted(self):
        root = self.studio()
        cloud = self.cloud_folder(files={
            "quarterly-plan.md": "# Q3 plan\n\nShip the thing.\n",
            "notes.txt": "call notes 2026-07-30\n",
        })
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)
        return root, cloud, record

    def test_adoption_writes_a_sidecar_beside_every_top_level_file(self) -> None:
        """`<folder>/.tropo-studio/<filename>.tropo.md` — the frozen location.

        The path matters as much as the existence: `rebuild-vault` walks
        `**/.tropo-studio/*.tropo.md`, and a sidecar written anywhere else is
        invisible to the rebuild that invariant 8 promises.
        """
        root, cloud, _record = self.adopted()
        sources = sorted(p.name for p in cloud.iterdir() if p.is_file())
        self.assertPlanted(sources, "the fixture folder has no files to adopt")

        for name in sources:
            with self.subTest(source=name):
                self.assertTrue(
                    (cloud / SIDECAR_DIR / f"{name}.tropo.md").is_file(),
                    msg=f"no sidecar at {SIDECAR_DIR}/{name}.tropo.md",
                )

    def test_every_sidecar_points_at_a_real_file_with_a_matching_hash(self) -> None:
        """Depth-agnostic, because the surface does not fix a recursion depth.

        Whatever set of files the build decides to sidecar, each sidecar has to
        resolve to a file that is actually there and hash to what it claims.
        `source_hash` is also the structural egress mark, so a wrong one is two
        defects at once.
        """
        root, cloud, _record = self.adopted()
        sidecars = self.sidecars_in(cloud)
        self.assertPlanted(sidecars, "adoption wrote no sidecars at all")

        for sidecar in sidecars:
            with self.subTest(sidecar=sidecar.name):
                front = frontmatter(sidecar)
                target = (sidecar.parent / str(front.get("source_path", ""))).resolve()
                self.assertTrue(
                    target.is_file(),
                    msg=f"{sidecar.name} points at {front.get('source_path')!r}, "
                        "which resolves to nothing",
                )
                self.assertEqual(
                    front.get("source_hash"), sha256_of(target),
                    msg=f"{sidecar.name} records a hash that is not the file's",
                )

    def test_unquoted_numeric_leading_zero_uid_keeps_all_eight_characters(
        self,
    ) -> None:
        """Historical sidecars cannot lose identity through scalar coercion."""
        sidecar = self._tmp / "historical.tropo.md"
        sidecar.write_text(
            "---\n"
            "uid: 01234567\n"
            "type: external-artifact\n"
            "---\n",
            encoding="utf-8",
        )

        parsed = folder.walker.parse_frontmatter(sidecar)

        self.assertEqual(parsed["uid"], "01234567")

    def test_the_projection_is_derived_from_the_sidecar_and_names_it(self) -> None:
        """`vault/files/<uid>.md` is a projection, and it says so on its face.

        The uid is minted into the sidecar and carried to the projection, and
        the projection carries the edge back. Without that edge there is no way
        for a rebuild to know which sidecar re-derives which entry, and
        "projections are derived" becomes an unenforceable claim.
        """
        root, cloud, _record = self.adopted()
        sidecars = self.sidecars_in(cloud)
        self.assertPlanted(sidecars, "adoption wrote no sidecars at all")

        for sidecar in sidecars:
            with self.subTest(sidecar=sidecar.name):
                uid = frontmatter(sidecar).get("uid")
                self.assertIsNotNone(uid, msg=f"{sidecar.name} carries no uid")
                projection = root / "vault" / "files" / f"{uid}.md"
                self.assertTrue(
                    projection.is_file(),
                    msg=f"no governed entry derived from {sidecar.name} at "
                        f"vault/files/{uid}.md",
                )
                derived = frontmatter(projection)
                self.assertEqual(derived.get("uid"), uid)
                handle = resolve_recorded(
                    derived.get("source_sidecar"),
                    studio_root=root,
                    projection_dir=projection.parent,
                    mount_path=cloud,
                )
                self.assertEqual(
                    handle, sidecar.resolve(),
                    msg="the projection does not name the sidecar it was "
                        f"derived from (source_sidecar="
                        f"{derived.get('source_sidecar')!r})",
                )

    def test_a_projection_that_contradicts_its_sidecar_loses_to_the_sidecar(self) -> None:
        """The only test of "canonical" that means anything: make them disagree.

        Invariant 8 says primary metadata must round-trip through the sidecar
        and that walking sidecars reproduces the vault. So when the two
        surfaces conflict, reconciliation flows one way. An implementation that
        reads the projection and repairs the sidecar passes every existence
        check above and fails here, which is the whole reason this case is
        written as a conflict rather than as a rebuild.
        """
        root, cloud, record = self.adopted()
        sidecars = self.sidecars_in(cloud)
        self.assertPlanted(sidecars, "adoption wrote no sidecars at all")
        sidecar = sidecars[0]
        truth = frontmatter(sidecar)
        uid = truth.get("uid")
        projection = root / "vault" / "files" / f"{uid}.md"
        self.assertPlanted(projection.is_file(), f"no projection for sidecar {sidecar.name}")

        sidecar_bytes_before = sidecar.read_bytes()
        forged = "deadbeef" * 8
        lie, substitutions = re.subn(
            r"^source_hash:.*$", f"source_hash: {forged}",
            projection.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE,
        )
        self.assertPlanted(substitutions == 1, "the projection records no source_hash to corrupt")
        projection.write_text(lie, encoding="utf-8")
        self.assertPlanted(
            frontmatter(projection).get("source_hash") == forged
            and truth.get("source_hash") != forged,
            "the projection was supposed to be corrupted into disagreeing with "
            "its sidecar; if the substitution missed, this case proves nothing",
        )

        folder.reconcile(root, record.mount_uid)

        self.assertEqual(
            sidecar.read_bytes(), sidecar_bytes_before,
            msg="reconcile rewrote the SIDECAR to match a corrupted "
                "projection. Projections are derived and never authoritative "
                "(TROPO-CONTROL invariant 8).",
        )
        self.assertEqual(
            frontmatter(projection).get("source_hash"), truth.get("source_hash"),
            msg="reconcile left the projection contradicting its sidecar. The "
                "sidecar is canonical, so the projection is what gets fixed.",
        )


# --------------------------------------------------------------------------- #
# Mounted-content availability + deterministic derived projections             #
# --------------------------------------------------------------------------- #

class MountedAvailabilityTests(FolderCase):
    """Phase 1: offline is a tombstone state, not an implicit unmount."""

    def adopted(self):
        root = self.studio()
        cloud = self.cloud_folder(files={
            "quarterly-plan.md": "# Q3 plan\n\nCapgemini source-only words.\n",
        })
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)
        return root, cloud, record

    def downgrade_to_live_schema1(
        self,
        root: Path,
        record,
    ) -> set[str]:
        """Reproduce the live registry/projection shape from this Studio."""
        registry_path = root / folder.MOUNT_REGISTRY_REL
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        current = registry["mounts"][record.mount_uid]
        owned = set(current["projection_uids"])
        live_fields = (
            "adopted_at",
            "fingerprint",
            "last_checked",
            "mounted_at",
            "mounted_by",
            "name",
            "path",
            "state",
        )
        registry_path.write_text(
            json.dumps(
                {
                    "mounts": {
                        record.mount_uid: {
                            key: current[key]
                            for key in live_fields
                            if key in current
                        }
                    },
                    "schema_version": 1,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        for uid in owned:
            projection = root / "vault" / "files" / f"{uid}.md"
            projection.write_text(
                projection.read_text(encoding="utf-8").replace(
                    "projection_authority: derived-only\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )
        legacy_projection = next(
            path
            for path in self.projections_in(root)
            if path.stem in owned
            and frontmatter(path).get("type") == "external-artifact"
        )
        legacy_projection.write_text(
            legacy_projection.read_text(encoding="utf-8").replace(
                "governance: tier-1-sidecar\n",
                "governance: tier-1-projection\n",
                1,
            ),
            encoding="utf-8",
        )
        live_raw = json.loads(
            registry_path.read_text(encoding="utf-8")
        )["mounts"][record.mount_uid]
        _authority, suspects = folder._mount_projection_authority(
            root, record.mount_uid, live_raw
        )
        self.assertFalse(
            suspects,
            msg=f"live-shape fixture did not carry complete ownership proof: {suspects}",
        )
        return owned

    def index_rows(self, root: Path) -> dict:
        return {
            row["uid"]: row
            for row in (
                json.loads(line)
                for line in (root / "vault" / "00-index.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            )
        }

    def take_offline(self, cloud: Path) -> Path:
        offline = self._tmp / "offline-device" / cloud.name
        offline.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cloud), str(offline))
        self.assertPlanted(not cloud.exists() and offline.is_dir(),
                           "the mounted folder was not taken offline")
        return offline

    def seal_index(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "fixture@test.local"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "fixture"],
            cwd=root,
            check=True,
        )
        (root / ".gitignore").write_text(
            ".tropo-studio/\n"
            "vault/00-index.jsonl\n"
            "vault/00-archive-index.jsonl\n"
            "vault/00-index.sqlite\n"
            "vault/00-project-tree.jsonl\n"
            "recycle/\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", ".gitignore", "STUDIO.md", "vault/files"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture sources"],
            cwd=root,
            check=True,
        )
        self.assertEqual(
            rebuild_index.rebuild_index(root, True, reconcile=True),
            0,
        )
        # A strict read is the contract's seal check, not merely JSON syntax.
        rebuild_index.index_surfaces.read_jsonl_strict(
            root / "vault" / "00-index.jsonl"
        )
        rebuild_index.index_surfaces.read_jsonl_strict(
            root / "vault" / "00-archive-index.jsonl"
        )

    def test_sidecar_uid_collision_refuses_without_changing_any_byte(self):
        root, _cloud, record = self.adopted()
        projection = self.projections_in(root)[0]
        uid = projection.stem
        projection.write_text(
            "---\n"
            f"uid: {uid}\n"
            "type: note\n"
            "status: active\n"
            "title: ordinary governed note\n"
            "---\n\nHuman-authored body.\n",
            encoding="utf-8",
        )
        before = tree_digest(root)

        with self.assertRaisesRegex(folder.FolderMountError, "UID_COLLISION"):
            folder.reconcile(root, record.mount_uid)

        self.assertEqual(tree_digest(root), before)

    def test_registry_swap_failure_rolls_back_projection_and_every_surface(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        projections = {
            path: path.read_bytes() for path in self.projections_in(root)
        }
        registry = root / folder.MOUNT_REGISTRY_REL
        participants = (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
            root / rebuild_index.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            root / rebuild_index.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            rebuild_index._dirty_counter_path(root),
            registry,
        )
        before = tuple(path.read_bytes() for path in participants)
        self.take_offline(cloud)
        real_replace = folder.index_writer.index_surfaces.os.replace

        def fail_registry(src, dst):
            if Path(dst) == registry:
                raise OSError("reviewer-injected registry swap failure")
            return real_replace(src, dst)

        with mock.patch.object(
            folder.index_writer.index_surfaces.os,
            "replace",
            side_effect=fail_registry,
        ):
            with self.assertRaises(folder.FolderMountError):
                folder.reconcile(root, record.mount_uid)

        self.assertEqual(
            {path: path.read_bytes() for path in projections},
            projections,
        )
        self.assertEqual(
            tuple(path.read_bytes() for path in participants),
            before,
        )

    def test_interrupted_projection_transaction_recovers_and_retry_converges(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        registry = root / folder.MOUNT_REGISTRY_REL
        self.take_offline(cloud)
        real_replace = folder.index_writer.index_surfaces.os.replace
        interrupted = False

        def interrupt_registry(src, dst):
            nonlocal interrupted
            if Path(dst) == registry and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("reviewer-injected crash")
            return real_replace(src, dst)

        with mock.patch.object(
            folder.index_writer.index_surfaces.os,
            "replace",
            side_effect=interrupt_registry,
        ):
            with self.assertRaises(KeyboardInterrupt):
                folder.reconcile(root, record.mount_uid)

        journal = (
            root
            / folder.index_writer.index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
        )
        self.assertTrue(journal.is_file())

        report = folder.reconcile(root, record.mount_uid)

        self.assertFalse(journal.exists())
        self.assertEqual(report.lost, 1)
        stored = json.loads(registry.read_text(encoding="utf-8"))
        self.assertEqual(
            stored["mounts"][record.mount_uid]["availability"],
            "unavailable",
        )
        rows = self.index_rows(root)
        for projection in self.projections_in(root):
            self.assertEqual(frontmatter(projection)["availability"], "unavailable")
            self.assertEqual(rows[projection.stem]["availability"], "unavailable")
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
            sqlite_rows = {
                uid: json.loads(raw)["availability"]
                for uid, raw in conn.execute(
                    "SELECT uid, fm_json FROM entries"
                )
                if uid in rows
            }
        self.assertTrue(sqlite_rows)
        self.assertEqual(set(sqlite_rows.values()), {"unavailable"})

    def test_crash_then_concurrent_mounts_recover_before_registry_rmw(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        registry = root / folder.MOUNT_REGISTRY_REL
        self.take_offline(cloud)
        real_replace = folder.index_writer.index_surfaces.os.replace
        interrupted = False

        def interrupt_registry(src, dst):
            nonlocal interrupted
            if Path(dst) == registry and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("reviewer-injected registry crash")
            return real_replace(src, dst)

        with mock.patch.object(
            folder.index_writer.index_surfaces.os,
            "replace",
            side_effect=interrupt_registry,
        ):
            with self.assertRaises(KeyboardInterrupt):
                folder.reconcile(root, record.mount_uid)

        journal = (
            root
            / folder.index_writer.index_surfaces.INDEX_TRANSACTION_RELATIVE_PATH
        )
        self.assertTrue(journal.is_file())
        clouds = (
            self.cloud_folder(parent="post-crash-a", leaf="Finance"),
            self.cloud_folder(parent="post-crash-b", leaf="Legal"),
        )
        barrier = threading.Barrier(3)
        mounted = []
        failures = []

        def attach(cloud_path: Path, name: str) -> None:
            try:
                barrier.wait(timeout=5)
                mounted.append(folder.mount(root, cloud_path, name=name))
            except Exception as exc:
                failures.append(exc)

        threads = [
            threading.Thread(target=attach, args=(clouds[0], "Finance")),
            threading.Thread(target=attach, args=(clouds[1], "Legal")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(failures)
        self.assertFalse(journal.exists())
        stored = json.loads(registry.read_text(encoding="utf-8"))["mounts"]
        self.assertEqual(
            set(stored),
            {record.mount_uid, *(item.mount_uid for item in mounted)},
        )
        self.assertEqual(stored[record.mount_uid]["availability"], "available")

    def test_unmount_blocks_all_live_structured_relationship_aliases(self):
        root, _cloud, record = self.adopted()
        target_uid = self.projections_in(root)[0].stem
        source_uid = "f0f0f0f0"
        source = root / "vault" / "files" / f"{source_uid}.md"
        source.write_text(
            "---\n"
            f"uid: {source_uid}\n"
            "type: note\n"
            "status: active\n"
            "title: surviving dependent\n"
            "relations:\n"
            "  - rel: member_of\n"
            f"    uid: {target_uid}\n"
            "relationships:\n"
            "  - type: governed_by\n"
            f"    to: {target_uid}\n"
            "created: '2026-08-02'\n"
            "modified: '2026-08-02'\n"
            "extraction_scope: ship\n"
            "---\n\nSurviving entry.\n",
            encoding="utf-8",
        )
        self.seal_index(root)
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid = ? "
                    "ORDER BY rel, dst_uid",
                    (source_uid,),
                ).fetchall(),
                [("governed_by", target_uid), ("member_of", target_uid)],
            )
        before = tree_digest(root)

        with self.assertRaises(folder.FolderMountError) as raised:
            folder.unmount(root, record.mount_uid)

        self.assertIn("member_of", str(raised.exception))
        self.assertIn("governed_by", str(raised.exception))
        self.assertIn("surviving dependent", str(raised.exception))
        self.assertEqual(tree_digest(root), before)

    def test_live_schema1_offline_unmount_removes_every_owned_surface(self):
        root, cloud, record = self.adopted()
        owned = self.downgrade_to_live_schema1(root, record)
        self.seal_index(root)
        artifact = next(
            path
            for path in self.projections_in(root)
            if path.stem in owned
            and frontmatter(path).get("type") == "external-artifact"
        )
        artifact.write_text(
            artifact.read_text(encoding="utf-8").replace(
                "status: active\n",
                "status: superseded\n",
                1,
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            rebuild_index.freshen_many({artifact.stem}, root),
            0,
        )
        current_before = {
            row["uid"]
            for row in rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / "00-index.jsonl"
            )
        }
        archive_before = {
            row["uid"]
            for row in rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / "00-archive-index.jsonl"
            )
        }
        self.assertTrue(owned & current_before)
        self.assertTrue(owned & archive_before)
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            placeholders = ",".join("?" for _ in owned)
            self.assertEqual(
                connection.execute(
                    f"SELECT COUNT(*) FROM entries WHERE uid IN ({placeholders})",
                    tuple(sorted(owned)),
                ).fetchone()[0],
                len(owned),
            )
            self.assertGreater(
                connection.execute(
                    f"SELECT COUNT(*) FROM edges WHERE src_uid IN ({placeholders}) "
                    f"OR dst_uid IN ({placeholders})",
                    (*sorted(owned), *sorted(owned)),
                ).fetchone()[0],
                0,
            )
        self.take_offline(cloud)

        folder.unmount(root, record.mount_uid)

        stored = json.loads(
            (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
        )
        self.assertEqual(stored["schema_version"], 2)
        self.assertNotIn(record.mount_uid, stored["mounts"])
        for name in ("00-index.jsonl", "00-archive-index.jsonl"):
            rows = rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / name
            )
            self.assertTrue(owned.isdisjoint({row["uid"] for row in rows}))
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            placeholders = ",".join("?" for _ in owned)
            for table in ("entries", "entries_fts"):
                self.assertEqual(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} "
                        f"WHERE uid IN ({placeholders})",
                        tuple(sorted(owned)),
                    ).fetchone()[0],
                    0,
                )
            self.assertEqual(
                connection.execute(
                    f"SELECT COUNT(*) FROM edges "
                    f"WHERE src_uid IN ({placeholders}) "
                    f"OR dst_uid IN ({placeholders})",
                    (*sorted(owned), *sorted(owned)),
                ).fetchone()[0],
                0,
            )

    def test_live_schema1_migration_preserves_mount_and_file_identities(self):
        root, cloud, record = self.adopted()
        owned = self.downgrade_to_live_schema1(root, record)
        sidecar_uids = {
            str(frontmatter(path).get("uid"))
            for path in cloud.rglob(".tropo-studio/*.tropo.md")
        }
        projection_uids = {
            path.stem: str(frontmatter(path).get("uid"))
            for path in self.projections_in(root)
            if path.stem in owned
        }
        second = self.cloud_folder(parent="schema2-migration", leaf="Legal")

        folder.mount(root, second, name="Legal")

        migrated = json.loads(
            (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
        )
        self.assertEqual(migrated["schema_version"], 2)
        self.assertIn(record.mount_uid, migrated["mounts"])
        self.assertEqual(
            set(migrated["mounts"][record.mount_uid]["projection_uids"]),
            owned,
        )
        self.assertEqual(
            {
                path.stem: str(frontmatter(path).get("uid"))
                for path in self.projections_in(root)
                if path.stem in owned
            },
            projection_uids,
        )
        self.assertEqual(
            {
                str(frontmatter(path).get("uid"))
                for path in cloud.rglob(".tropo-studio/*.tropo.md")
            },
            sidecar_uids,
        )

    def test_unverified_live_schema1_projection_refuses_without_mutation(self):
        root, _cloud, record = self.adopted()
        owned = self.downgrade_to_live_schema1(root, record)
        artifact = next(
            path
            for path in self.projections_in(root)
            if path.stem in owned
            and frontmatter(path).get("type") == "external-artifact"
        )
        artifact.write_text(
            artifact.read_text(encoding="utf-8").replace(
                "source_sidecar:",
                "untrusted_source_sidecar:",
                1,
            ),
            encoding="utf-8",
        )
        before = tree_digest(root, skip_dirs=("locks",))

        with self.assertRaises(folder.FolderMountError) as raised:
            folder.unmount(root, record.mount_uid)

        self.assertIn("cannot safely migrate legacy mount", str(raised.exception))
        self.assertEqual(
            tree_digest(root, skip_dirs=("locks",)),
            before,
        )
        self.assertIn(
            record.mount_uid,
            json.loads(
                (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
            )["mounts"],
        )

    def test_unmount_interruption_after_move_is_durably_recoverable(self):
        root, _cloud, record = self.adopted()
        self.seal_index(root)
        projections = {
            path: path.read_bytes() for path in self.projections_in(root)
        }
        registry = root / folder.MOUNT_REGISTRY_REL
        participants = (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
            root / rebuild_index.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            root / rebuild_index.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            registry,
        )
        before = tuple(path.read_bytes() for path in participants)

        with mock.patch.object(
            folder.index_writer,
            "remove_many",
            side_effect=KeyboardInterrupt("reviewer-injected post-move crash"),
        ):
            with self.assertRaises(KeyboardInterrupt):
                folder.unmount(root, record.mount_uid)

        intent = root / folder.UNMOUNT_MOVE_INTENT_REL
        self.assertTrue(intent.is_file())
        self.assertTrue(any(not path.exists() for path in projections))

        folder.recover_pending_folder_transactions(root)

        self.assertFalse(intent.exists())
        self.assertEqual(
            {path: path.read_bytes() for path in projections},
            projections,
        )
        self.assertEqual(
            tuple(path.read_bytes() for path in participants),
            before,
        )
        recycle_date = (
            root
            / "recycle"
            / "agent-deletions"
            / datetime.now().strftime("%Y-%m-%d")
        )
        self.assertFalse(recycle_date.exists())

    def test_unmount_removes_index_rows_when_projection_file_is_missing(self):
        root, _cloud, record = self.adopted()
        self.seal_index(root)
        registry = json.loads(
            (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
        )
        owned = set(registry["mounts"][record.mount_uid]["projection_uids"])
        missing_uid = sorted(owned)[0]
        (root / "vault" / "files" / f"{missing_uid}.md").unlink()

        result = folder.unmount(root, record.mount_uid)

        self.assertNotIn(missing_uid, result["recycled"])
        self.assertNotIn(
            record.mount_uid,
            json.loads(
                (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
            )["mounts"],
        )
        rows = []
        for name in ("00-index.jsonl", "00-archive-index.jsonl"):
            rows.extend(
                rebuild_index.index_surfaces.read_jsonl_strict(
                    root / "vault" / name
                )
            )
        self.assertTrue(owned.isdisjoint({row["uid"] for row in rows}))
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as conn:
            for table in ("entries", "entries_fts"):
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE uid IN "
                    f"({','.join('?' for _ in owned)})",
                    tuple(sorted(owned)),
                ).fetchone()[0]
                self.assertEqual(count, 0)
            edge_count = conn.execute(
                f"SELECT COUNT(*) FROM edges WHERE src_uid IN "
                f"({','.join('?' for _ in owned)}) "
                f"OR dst_uid IN ({','.join('?' for _ in owned)})",
                (*sorted(owned), *sorted(owned)),
            ).fetchone()[0]
            self.assertEqual(edge_count, 0)

    def test_unmount_registry_swap_failure_restores_files_index_and_registry(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        self.take_offline(cloud)
        folder.reconcile(root, record.mount_uid)
        projections = {
            path: path.read_bytes() for path in self.projections_in(root)
        }
        registry = root / folder.MOUNT_REGISTRY_REL
        participants = (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
            root / rebuild_index.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            root / rebuild_index.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            rebuild_index._dirty_counter_path(root),
            registry,
        )
        before = tuple(path.read_bytes() for path in participants)
        real_replace = folder.index_writer.index_surfaces.os.replace

        def fail_registry(src, dst):
            if Path(dst) == registry:
                raise OSError("reviewer-injected unmount registry failure")
            return real_replace(src, dst)

        with mock.patch.object(
            folder.index_writer.index_surfaces.os,
            "replace",
            side_effect=fail_registry,
        ):
            with self.assertRaises(folder.FolderMountError):
                folder.unmount(root, record.mount_uid)

        self.assertEqual(
            {path: path.read_bytes() for path in projections},
            projections,
        )
        self.assertEqual(
            tuple(path.read_bytes() for path in participants),
            before,
        )
        recycle_date = (
            root
            / "recycle"
            / "agent-deletions"
            / datetime.now().strftime("%Y-%m-%d")
        )
        self.assertFalse(recycle_date.exists())

    def test_unavailable_preserves_stub_and_index_identity_without_stale_edges(self):
        root, cloud, record = self.adopted()
        uid_by_sidecar = {
            p.name: frontmatter(p)["uid"] for p in self.sidecars_in(cloud)
        }
        projection_names = [p.name for p in self.projections_in(root)]
        self.take_offline(cloud)

        report = folder.reconcile(root, record.mount_uid)

        self.assertEqual(report.lost, 1)
        mounted = self.only_mount(root)
        self.assertEqual(mounted.mount_uid, record.mount_uid)
        self.assertEqual(mounted.availability, folder.AVAILABILITY_UNAVAILABLE)
        self.assertEqual([p.name for p in self.projections_in(root)], projection_names)
        self.assertIn("quarterly-plan.md",
                      [item["name"] for item in report.affected_files])
        rows = self.index_rows(root)
        for uid in uid_by_sidecar.values():
            projection = root / "vault" / "files" / f"{uid}.md"
            projected = frontmatter(projection)
            self.assertEqual(projected["uid"], uid)
            self.assertEqual(projected["availability"], "unavailable")
            self.assertNotIn("source_path", projected)
            self.assertNotIn("source_sidecar", projected)
            self.assertNotIn("member_of", projected)
            self.assertNotIn("**Source:**", projection.read_text(encoding="utf-8"))
            self.assertEqual(rows[uid]["uid"], uid)
            self.assertEqual(rows[uid]["availability"], "unavailable")
            self.assertNotIn("source_path", rows[uid])
            self.assertFalse(rows[uid].get("member_of"))

    def test_refind_restores_available_on_the_same_mount_and_file_uids(self):
        root, cloud, record = self.adopted()
        file_uids = sorted(p.stem for p in self.projections_in(root))
        offline = self.take_offline(cloud)
        folder.reconcile(root, record.mount_uid)

        report = folder.reconcile(
            root, record.mount_uid, resolve_path=offline
        )

        self.assertEqual(report.moved, 1)
        self.assertEqual(self.only_mount(root).mount_uid, record.mount_uid)
        self.assertEqual(
            self.only_mount(root).availability, folder.AVAILABILITY_AVAILABLE
        )
        self.assertEqual(sorted(p.stem for p in self.projections_in(root)), file_uids)
        for projection in self.projections_in(root):
            self.assertEqual(frontmatter(projection)["availability"], "available")
        self.assertTrue(
            all(row["availability"] == "available"
                for uid, row in self.index_rows(root).items() if uid in file_uids)
        )

    def test_full_regeneration_is_byte_identical_on_the_second_pass(self):
        root, _cloud, record = self.adopted()
        folder.reconcile(root, record.mount_uid)
        first = {p.name: p.read_bytes() for p in self.projections_in(root)}

        second_report = folder.reconcile(root, record.mount_uid)
        second = {p.name: p.read_bytes() for p in self.projections_in(root)}

        self.assertEqual(second, first)
        self.assertEqual(second_report.projections_repaired, 0)
        self.assertEqual(second_report.projections_tampered, [])

    def test_forged_stub_is_fully_repaired_and_explicitly_reported(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        truth = frontmatter(sidecar)
        projection = root / "vault" / "files" / f"{truth['uid']}.md"
        forged = re.sub(
            r"^source_hash:.*$", "source_hash: " + "f" * 64,
            projection.read_text(encoding="utf-8"), count=1,
            flags=re.MULTILINE,
        ) + "\nFORGED HAND EDIT\n"
        projection.write_text(forged, encoding="utf-8")

        report = folder.reconcile(root, record.mount_uid)

        self.assertEqual(frontmatter(projection)["source_hash"], truth["source_hash"])
        self.assertNotIn("FORGED HAND EDIT", projection.read_text(encoding="utf-8"))
        self.assertIn(
            truth["uid"], [item["uid"] for item in report.projections_tampered]
        )

    def test_orphan_sidecar_is_named_nonzero_and_never_reminted(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        uid = frontmatter(sidecar)["uid"]
        source = cloud / frontmatter(sidecar)["source_filename"]
        projection_names = [p.name for p in self.projections_in(root)]
        source.unlink()
        self.assertPlanted(sidecar.is_file() and not source.exists(),
                           "the orphan sidecar fixture did not form")

        report = folder.reconcile(root, record.mount_uid)

        self.assertEqual([p.name for p in self.projections_in(root)], projection_names)
        self.assertEqual(
            report.orphan_sidecars,
            [{
                "sidecar_path": str(sidecar),
                "uid": uid,
                "missing_source": str(source),
            }],
        )
        self.assertEqual(frontmatter(
            root / "vault" / "files" / f"{uid}.md"
        )["availability"], "unavailable")
        output = io.StringIO()
        with redirect_stdout(output):
            code = folder.main([
                "reconcile", record.mount_uid, "--root", str(root), "--json",
            ])
        self.assertNotEqual(code, 0)
        self.assertIn(str(sidecar), output.getvalue())
        self.assertEqual([p.name for p in self.projections_in(root)], projection_names)

    def test_explicit_unmount_still_forgets_and_recycles_instead_of_tombstoning(self):
        root, cloud, record = self.adopted()
        source_before = self.source_digest(cloud)
        sidecars_before = {
            p.relative_to(cloud).as_posix(): p.read_bytes()
            for p in self.sidecars_in(cloud)
        }
        projections = self.projections_in(root)

        result = folder.unmount(root, record.mount_uid)

        self.assertEqual(folder.mounts(root), [])
        self.assertEqual(sorted(result["recycled"]), sorted(p.stem for p in projections))
        self.assertEqual(self.source_digest(cloud), source_before)
        self.assertEqual(
            {p.relative_to(cloud).as_posix(): p.read_bytes()
             for p in self.sidecars_in(cloud)},
            sidecars_before,
        )

    def test_sealed_offline_and_restore_advance_every_index_surface_together(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        mounted_uid = frontmatter(sidecar)["uid"]
        target_uid = "aaaaaaaa"
        inbound_uid = "bbbbbbbb"
        sidecar.write_text(
            sidecar.read_text(encoding="utf-8").replace(
                "governance: tier-1-sidecar\n",
                "governance: tier-1-sidecar\n"
                "refs:\n"
                f'  - "{target_uid}"\n',
            ),
            encoding="utf-8",
        )
        folder.reconcile(root, record.mount_uid)
        for uid, title, refs, state, status in (
            (target_uid, "edge target", [], "archived", "done"),
            (inbound_uid, "inbound referrer", [mounted_uid], "active", "active"),
        ):
            refs_block = "".join(f'  - "{item}"\n' for item in refs)
            (root / "vault" / "files" / f"{uid}.md").write_text(
                "---\n"
                f'uid: "{uid}"\n'
                "type: note\n"
                f'title: "{title}"\n'
                f"status: {status}\n"
                f"state: {state}\n"
                + ("refs:\n" + refs_block if refs else "")
                + "created: '2026-08-02'\n"
                "modified: '2026-08-02'\n"
                "schema_version: 2\n"
                "---\n\n"
                f"# {title}\n",
                encoding="utf-8",
            )
        self.seal_index(root)
        archive_cache = root / rebuild_index.ARCHIVE_CACHE_JSONL_REL
        archive_meta = root / rebuild_index.ARCHIVE_CACHE_META_REL
        archive_cache.parent.mkdir(parents=True, exist_ok=True)
        archive_cache.write_text("stale\n", encoding="utf-8")
        archive_meta.write_text("{}\n", encoding="utf-8")
        offline = self.take_offline(cloud)

        folder.reconcile(root, record.mount_uid)

        current_rows = {
            row["uid"]: row
            for row in rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / "00-index.jsonl"
            )
        }
        archive_rows = {
            row["uid"]: row
            for row in rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / "00-archive-index.jsonl"
            )
        }
        self.assertEqual(current_rows[mounted_uid]["availability"], "unavailable")
        self.assertIn(target_uid, archive_rows)
        self.assertNotIn("refs", current_rows[mounted_uid])
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            availability = connection.execute(
                "SELECT json_extract(fm_json, '$.availability') "
                "FROM entries WHERE uid=?",
                (mounted_uid,),
            ).fetchone()[0]
            outgoing = connection.execute(
                "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                (mounted_uid,),
            ).fetchall()
            inbound = connection.execute(
                "SELECT src_uid, rel FROM edges WHERE dst_uid=?",
                (mounted_uid,),
            ).fetchall()
            fts_body = connection.execute(
                "SELECT body FROM entries_fts WHERE uid=?",
                (mounted_uid,),
            ).fetchone()[0]
        self.assertEqual(availability, "unavailable")
        self.assertEqual(outgoing, [])
        self.assertIn((inbound_uid, "refs"), inbound)
        self.assertNotIn("**Source:**", fts_body)
        self.assertEqual(
            rebuild_index.index_surfaces._load_sqlite_ratchet_evidence(root),
            rebuild_index.index_surfaces._load_ratchet_evidence(root),
        )
        self.assertFalse(archive_cache.exists())
        self.assertFalse(archive_meta.exists())

        folder.reconcile(root, record.mount_uid, resolve_path=offline)

        restored_rows = {
            row["uid"]: row
            for row in rebuild_index.index_surfaces.read_jsonl_strict(
                root / "vault" / "00-index.jsonl"
            )
        }
        self.assertEqual(restored_rows[mounted_uid]["availability"], "available")
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            self.assertIn(
                ("refs", target_uid),
                connection.execute(
                    "SELECT rel, dst_uid FROM edges WHERE src_uid=?",
                    (mounted_uid,),
                ).fetchall(),
            )
            self.assertIn(
                (inbound_uid, "refs"),
                connection.execute(
                    "SELECT src_uid, rel FROM edges WHERE dst_uid=?",
                    (mounted_uid,),
                ).fetchall(),
            )
        self.assertEqual(
            rebuild_index.index_surfaces._load_sqlite_ratchet_evidence(root),
            rebuild_index.index_surfaces._load_ratchet_evidence(root),
        )

    def test_regeneration_preserves_sidecar_metadata_and_moves_marker_location(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        marker = cloud / ".tropo-studio" / ".tropo-folder.md"
        planted = (
            "tags:\n"
            '  - "planted-tag"\n'
            "relations:\n"
            '  - "aaaaaaaa"\n'
            "governed_by: bbbbbbbb\n"
            "capsule_version: '9.7'\n"
            "original_styles:\n"
            "  page:\n"
            "    width_dxa: 9876\n"
            "    orientation: landscape\n"
            "  named_styles:\n"
            '    - id: "Heading1"\n'
            '      font_family: "Aptos"\n'
        )
        sidecar.write_text(
            sidecar.read_text(encoding="utf-8").replace(
                "created: ", planted + "created: ", 1
            ).replace("owner: import-walker", "owner: planted-owner", 1),
            encoding="utf-8",
        )
        moved = self._tmp / "sync" / "OneDrive - Acme (1)" / cloud.name
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cloud), str(moved))

        folder.reconcile(root, record.mount_uid, resolve_path=moved)

        moved_sidecar = self.sidecars_in(moved)[0]
        projection = root / "vault" / "files" / f"{frontmatter(moved_sidecar)['uid']}.md"
        projected = frontmatter(projection)
        authoritative = frontmatter(moved_sidecar)
        for key in (
            "owner", "tags", "relations", "governed_by", "capsule_version",
            "original_styles", "created", "created_by", "modified",
            "modified_by", "schema_version",
        ):
            self.assertEqual(projected[key], authoritative[key], key)
        moved_marker = moved / ".tropo-studio" / ".tropo-folder.md"
        marker_front = frontmatter(moved_marker)
        mirror = root / "vault" / "files" / f"{marker_front['uid']}.md"
        mirror_front = frontmatter(mirror)
        self.assertEqual(marker_front["original_path"], str(moved))
        self.assertEqual(mirror_front["original_path"], str(moved_marker))
        self.assertEqual(
            mirror_front["folder_marker_path"],
            str(moved_marker),
        )
        self.assertFalse(marker.exists())

    def test_offline_ownership_never_uses_a_source_path_prefix(self):
        root = self.studio()
        cloud = self.cloud_folder(files={
            "quarterly-plan.md": "# Q3 plan\n",
        })
        record = folder.mount(root, cloud, name="Marketing")
        ordinary_uid = "cccccccc"
        ordinary = root / "vault" / "files" / f"{ordinary_uid}.md"
        ordinary.write_text(
            "---\n"
            f"uid: {ordinary_uid}\n"
            "type: note\n"
            "title: ordinary note\n"
            f"mount_uid: {record.mount_uid}\n"
            "projection_authority: derived-only\n"
            f'source_path: "{cloud / "quarterly-plan.md"}"\n'
            "status: active\n"
            "created: 2026-08-02\n"
            "modified: 2026-08-02\n"
            "schema_version: 2\n"
            "---\n\n"
            "# ordinary body must survive\n",
            encoding="utf-8",
        )
        folder.adopt(root, record.mount_uid)
        before = ordinary.read_bytes()
        self.take_offline(cloud)

        folder.reconcile(root, record.mount_uid)

        self.assertEqual(ordinary.read_bytes(), before)

    def test_unsearched_missing_recorded_path_is_ambiguous_and_tombstoned(self):
        root, cloud, record = self.adopted()
        self.take_offline(cloud)
        outcome = folder.LocateOutcome(
            status=folder.LOCATED_UNSEARCHED,
            searched=folder.SEARCH_MAX_DIRS,
        )
        with mock.patch.object(folder, "locate", return_value=outcome):
            report = folder.reconcile(root, record.mount_uid)

        self.assertEqual(report.unsearched, 1)
        self.assertEqual(
            self.only_mount(root).availability,
            folder.AVAILABILITY_AMBIGUOUS,
        )
        self.assertTrue(report.affected_files)
        for projection in self.projections_in(root):
            if frontmatter(projection).get("mount_uid") == record.mount_uid:
                self.assertEqual(frontmatter(projection)["availability"], "ambiguous")
                self.assertNotIn("source_path", frontmatter(projection))
        self.assertEqual(report.mounts[0]["status"], folder.LOCATED_UNSEARCHED)

    def test_tamper_is_reported_with_path_drift_and_while_already_offline(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        uid = frontmatter(sidecar)["uid"]
        projection = root / "vault" / "files" / f"{uid}.md"
        projection.write_text(
            projection.read_text(encoding="utf-8").replace(
                "source_hash:", "source_hash: forged-", 1
            )
            + "\nFORGED DURING MOVE\n",
            encoding="utf-8",
        )
        moved = self._tmp / "sync" / "OneDrive - Acme (1)" / cloud.name
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cloud), str(moved))

        moved_report = folder.reconcile(
            root, record.mount_uid, resolve_path=moved
        )

        self.assertIn(uid, [item["uid"] for item in moved_report.projections_tampered])
        old_path = moved
        self.take_offline(old_path)
        folder.reconcile(root, record.mount_uid)
        projection.write_text(
            projection.read_text(encoding="utf-8").replace(
                "# quarterly-plan.md", "# FORGED OFFLINE", 1
            ),
            encoding="utf-8",
        )

        offline_report = folder.reconcile(root, record.mount_uid)

        self.assertIn(
            uid,
            [item["uid"] for item in offline_report.projections_tampered],
        )
        self.assertNotIn("FORGED OFFLINE", projection.read_text(encoding="utf-8"))

    def test_offline_tamper_reports_frontmatter_and_body_independently(self):
        root, cloud, record = self.adopted()
        sidecar = self.sidecars_in(cloud)[0]
        uid = frontmatter(sidecar)["uid"]
        projection = root / "vault" / "files" / f"{uid}.md"
        self.take_offline(cloud)
        folder.reconcile(root, record.mount_uid)

        projection.write_text(
            projection.read_text(encoding="utf-8").replace(
                "title:", "title: forged-", 1
            ),
            encoding="utf-8",
        )
        frontmatter_report = folder.reconcile(root, record.mount_uid)
        frontmatter_tamper = next(
            item for item in frontmatter_report.projections_tampered
            if item["uid"] == uid
        )
        self.assertEqual(frontmatter_tamper["edits"], ["frontmatter"])

        projection.write_text(
            projection.read_text(encoding="utf-8") + "\nFORGED BODY ONLY\n",
            encoding="utf-8",
        )
        body_report = folder.reconcile(root, record.mount_uid)
        body_tamper = next(
            item for item in body_report.projections_tampered
            if item["uid"] == uid
        )
        self.assertEqual(body_tamper["edits"], ["body"])

    def test_available_projection_writes_roll_back_with_index_companions(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        projections = self.projections_in(root)
        existing = projections[0]
        created_then_rolled_back = projections[1]
        existing.write_text(
            existing.read_text(encoding="utf-8") + "\nFORGED BEFORE REFUSAL\n",
            encoding="utf-8",
        )
        existing_before = existing.read_bytes()
        created_then_rolled_back.unlink()
        registry = root / folder.MOUNT_REGISTRY_REL
        cache_jsonl = root / rebuild_index.ARCHIVE_CACHE_JSONL_REL
        cache_meta = root / rebuild_index.ARCHIVE_CACHE_META_REL
        cache_jsonl.parent.mkdir(parents=True, exist_ok=True)
        cache_jsonl.write_bytes(b"stale cache\n")
        cache_meta.write_bytes(b'{"stale":true}\n')
        participants = (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
            root / rebuild_index.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            root / rebuild_index.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            cache_jsonl,
            cache_meta,
            rebuild_index._dirty_counter_path(root),
            registry,
        )
        before = tuple(path.read_bytes() for path in participants)
        dirty_counter = rebuild_index._dirty_counter_path(root)
        real_replace = folder.index_writer.index_surfaces.os.replace

        def fail_counter_swap(src, dst):
            if Path(dst) == dirty_counter:
                raise OSError("reviewer-injected projection companion failure")
            return real_replace(src, dst)

        with mock.patch.object(
            folder.index_writer.index_surfaces.os,
            "replace",
            side_effect=fail_counter_swap,
        ):
            with self.assertRaises(folder.FolderMountError):
                folder.reconcile(root, record.mount_uid)

        self.assertEqual(existing.read_bytes(), existing_before)
        self.assertFalse(created_then_rolled_back.exists())
        self.assertEqual(
            tuple(path.read_bytes() for path in participants),
            before,
        )

    def test_unavailable_tombstones_roll_back_when_index_refuses(self):
        root, cloud, record = self.adopted()
        self.seal_index(root)
        projections = self.projections_in(root)
        projection_bytes = {
            projection: projection.read_bytes() for projection in projections
        }
        registry = root / folder.MOUNT_REGISTRY_REL
        participants = (
            root / "vault" / "00-index.jsonl",
            root / "vault" / "00-archive-index.jsonl",
            root / "vault" / "00-index.sqlite",
            root / rebuild_index.index_surfaces.INDEX_SURFACE_META_RELATIVE_PATH,
            root / rebuild_index.index_surfaces.INDEX_RATCHET_RELATIVE_PATH,
            rebuild_index._dirty_counter_path(root),
            registry,
        )
        before = tuple(path.read_bytes() for path in participants)
        self.take_offline(cloud)

        with mock.patch.object(
            folder.index_writer,
            "freshen_many",
            return_value=1,
        ):
            with self.assertRaises(folder.FolderMountError):
                folder.reconcile(root, record.mount_uid)

        self.assertEqual(
            {
                projection: projection.read_bytes()
                for projection in projections
            },
            projection_bytes,
        )
        self.assertEqual(
            tuple(path.read_bytes() for path in participants),
            before,
        )

    def test_unmount_after_offline_removes_sealed_rows_and_failure_keeps_registry(self):
        root, cloud, record = self.adopted()
        owned_uids = {
            projection.stem for projection in self.projections_in(root)
        }
        self.seal_index(root)
        self.take_offline(cloud)
        folder.reconcile(root, record.mount_uid)

        with mock.patch.object(
            folder.index_writer, "remove_many", return_value=1
        ):
            with self.assertRaises(folder.FolderMountError):
                folder.unmount(root, record.mount_uid)
        self.assertEqual(self.only_mount(root).mount_uid, record.mount_uid)
        self.assertTrue(
            all((root / "vault" / "files" / f"{uid}.md").is_file()
                for uid in owned_uids)
        )
        recycle_date = (
            root / "recycle" / "agent-deletions"
            / datetime.now().strftime("%Y-%m-%d")
        )
        self.assertFalse(
            recycle_date.exists(),
            "failed unmount left a newly-created empty recycle date directory",
        )

        result = folder.unmount(root, record.mount_uid)

        self.assertEqual(set(result["recycled"]), owned_uids)
        self.assertEqual(folder.mounts(root), [])
        current = rebuild_index.index_surfaces.read_jsonl_strict(
            root / "vault" / "00-index.jsonl"
        )
        archive = rebuild_index.index_surfaces.read_jsonl_strict(
            root / "vault" / "00-archive-index.jsonl"
        )
        self.assertFalse(
            owned_uids & {row["uid"] for row in current + archive}
        )
        with sqlite3.connect(root / "vault" / "00-index.sqlite") as connection:
            placeholders = ",".join("?" for _ in owned_uids)
            self.assertEqual(
                connection.execute(
                    f"SELECT COUNT(*) FROM entries WHERE uid IN ({placeholders})",
                    tuple(owned_uids),
                ).fetchone()[0],
                0,
            )

    def test_capsule_records_mikes_lock_as_an_amendment_provenance_event(self):
        capsule = (
            LIVE_STUDIO / "vault" / "capsules"
            / "tropo-external-artifact.capsule.md"
        ).read_text(encoding="utf-8")
        self.assertIn("locked_by: argus-a62", capsule)
        self.assertIn("evt_4927862819e98650_00000003", capsule)
        self.assertIn("Mike", capsule)
        self.assertIn("modified_by: argus-a144", capsule)


# --------------------------------------------------------------------------- #
# Source files are never modified                                               #
# --------------------------------------------------------------------------- #

class SourceBytesTests(FolderCase):
    """The strongest form: hash everything before and after everything."""

    def test_no_operation_changes_a_single_source_byte(self) -> None:
        """Mount, adopt, list, reconcile — hashed between every one of them.

        Stated as the strongest form on purpose. This is somebody's OneDrive:
        the promise is not "we mostly leave it alone", and publishing back
        stays additive elsewhere through `tropo-export.py`'s `stem v-NN`
        scheme, which never overwrites. Hashing between each step means the
        report names the operation that broke the promise.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        baseline = self.source_digest(cloud)
        self.assertPlanted(
            len(baseline) >= 3,
            f"the fixture folder should hold several source files; saw {sorted(baseline)}",
        )

        record = folder.mount(root, cloud, name="Marketing")
        self.assertSourcesUnchanged(cloud, baseline, "mount()")

        folder.adopt(root, record.mount_uid)
        self.assertSourcesUnchanged(cloud, baseline, "adopt()")

        folder.mounts(root)
        self.assertSourcesUnchanged(cloud, baseline, "mounts()")

        folder.reconcile(root, record.mount_uid)
        self.assertSourcesUnchanged(cloud, baseline, "reconcile()")

        folder.reconcile(root)
        self.assertSourcesUnchanged(cloud, baseline, "reconcile() over every mount")

    def test_adoption_adds_nothing_outside_the_sidecar_directory(self) -> None:
        """Adoption earns exactly one directory in somebody else's folder.

        `<folder>/.tropo-studio/` is the sanctioned write; a converted copy, a
        `.tropoignore`, a lock file or a rendered export dropped beside the
        originals is not. The control requires that something WAS written,
        because "added nothing anywhere" would otherwise pass for an adopt that
        did nothing at all.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        before = tree_digest(cloud)
        record = folder.mount(root, cloud, name="Marketing")

        folder.adopt(root, record.mount_uid)

        after = tree_digest(cloud)
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
        self.assertPlanted(added, "adoption added no files at all, so this case saw nothing")
        self.assertEqual(removed, [], msg="adoption removed files from the mounted folder")
        self.assertEqual(changed, [], msg="adoption rewrote files in the mounted folder")
        stray = [p for p in added if f"/{SIDECAR_DIR}/" not in f"/{p}"]
        self.assertEqual(
            stray, [],
            msg=f"adoption wrote outside {SIDECAR_DIR}/: {stray}",
        )

    def test_a_move_and_a_reconcile_change_no_source_byte(self) -> None:
        """Drift repair is a bookkeeping operation, not a content operation.

        The tempting fix for a moved folder is to move it back, or to re-copy
        it somewhere the studio prefers. Both would show up here.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)
        baseline = self.source_digest(cloud)

        moved = self._tmp / "sync" / "OneDrive - Acme (1)" / "Marketing"
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cloud), str(moved))
        self.assertPlanted(not cloud.exists() and moved.is_dir(), "the folder did not move")

        folder.reconcile(root)

        self.assertSourcesUnchanged(moved, baseline, "reconcile() after a move")


# --------------------------------------------------------------------------- #
# Imported bodies must not reach a model                                        #
# --------------------------------------------------------------------------- #

class EgressTests(FolderCase):
    """Answered by the shipped classifier, never by a copy of its rules.

    `tropo-orient.py` reads the three marks of an outside origin off a governed
    file's own frontmatter — `type: external-artifact`, the `external`
    publishing label, and the importer's `source_hash` — and any one is enough.
    These cases point `orient.FILES` at the fixture vault and ask
    `egress_class` the question, so if the policy moves, these move with it.
    Restating the regexes here would create a second policy that agrees with
    the first only until somebody edits one of them.
    """

    def setUp(self) -> None:
        super().setUp()
        if _ORIENT_ERROR is not None:
            self.fail(
                "the shipped egress classifier would not load, so these cases "
                "cannot be answered against it and must not be skipped into "
                f"green: {_ORIENT_ERROR!r}"
            )

    def classifier_over(self, root: Path):
        """Point the real classifier at the fixture vault.

        Returns a callable. The patch is undone at cleanup; the control that it
        landed is `test_a_publishing_label_that_is_not_external_does_not_
        restrict_egress`, which needs a real, eligible, agent-authored entry to
        be visible through it.
        """
        patcher = mock.patch.object(orient, "FILES", root / "vault" / "files")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertPlanted(
            orient.FILES == root / "vault" / "files",
            "the classifier is still pointed at the live vault",
        )
        return lambda uid, records=None: orient.egress_class(uid, records or {})

    def plant_entry(self, root: Path, uid: str, extra: str) -> str:
        (root / "vault" / "files" / f"{uid}.md").write_text(
            "---\n"
            f"uid: {uid}\n"
            "title: planted\n"
            "status: active\n"
            "owner: talos\n"
            f"{extra}"
            "---\n\nbody\n",
            encoding="utf-8",
        )
        return uid

    def test_an_adopted_projection_is_not_eligible_to_reach_a_model(self) -> None:
        """The headline: adoption imports somebody else's words into the vault.

        Those words are not ours to send. Every governed entry adoption creates
        must classify as ineligible under the shipped gate — not "should", and
        not "unless somebody remembers to label it".
        """
        root = self.studio()
        cloud = self.cloud_folder(files={"quarterly-plan.md": "# Q3\n\nconfidential\n"})
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)
        classify = self.classifier_over(root)

        projections = self.projections_in(root)
        self.assertPlanted(projections, "adoption produced no governed entries to classify")
        for projection in projections:
            with self.subTest(projection=projection.name):
                self.assertEqual(
                    classify(projection.stem), "private",
                    msg=f"{projection.name} is eligible to be sent to a model. "
                        "It is an imported body; its words came from outside "
                        "the studio.",
                )

    def test_the_projection_carries_at_least_one_of_the_three_marks(self) -> None:
        """The tool's own obligation, separate from the classifier's answer.

        The classifier can only recognise an outside origin if the importer
        stamps one. Read against `orient._IMPORTED_MARKS` rather than a local
        list of regexes, so the two lanes cannot drift apart.
        """
        root = self.studio()
        cloud = self.cloud_folder(files={"quarterly-plan.md": "# Q3\n"})
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)

        projections = self.projections_in(root)
        self.assertPlanted(projections, "adoption produced no governed entries")
        for projection in projections:
            with self.subTest(projection=projection.name):
                block = frontmatter_block(projection)
                hits = [m.pattern for m in orient._IMPORTED_MARKS if m.search(block)]
                self.assertTrue(
                    hits,
                    msg=f"{projection.name} carries none of the three marks of "
                        "an outside origin, so nothing downstream can tell it "
                        f"apart from agent-authored work. frontmatter:\n{block}",
                )

    def test_each_of_the_three_marks_alone_is_enough(self) -> None:
        """Any one is enough — because any one of them can be edited away.

        Three independent marks is a redundancy design, not a checklist. If the
        gate ever starts requiring two, an entry that lost one to a hand-edit
        walks straight through.
        """
        root = self.studio()
        classify = self.classifier_over(root)
        marks = {
            "capsule-type": ("ea0c0de1", "type: external-artifact\n"),
            "publishing-label": ("ea0c0de2", "extraction_scope: external\n"),
            "source-hash": ("ea0c0de3", "source_hash: " + "a" * 64 + "\n"),
        }
        for label, (uid, extra) in marks.items():
            with self.subTest(mark=label):
                self.plant_entry(root, uid, extra)
                self.assertPlanted(
                    (root / "vault" / "files" / f"{uid}.md").is_file(),
                    f"the {label} fixture entry was not written",
                )
                self.assertEqual(
                    classify(uid), "private",
                    msg=f"the {label} mark alone did not keep the body home",
                )

    def test_a_publishing_label_that_is_not_external_does_not_restrict_egress(self) -> None:
        """The mistake this Studio has now made three times, pinned as a case.

        `extraction_scope` answers "may this go on the website". Whether a
        document may cross to a model provider is a different question with a
        different answer, and deriving one from the other is what made 2,400
        agent-authored records ineligible for a reason that had nothing to do
        with models. Only the literal `external` value is a mark; every other
        value is a publishing label and must leave egress alone.

        This case is also the control that the classifier patch landed: the
        real entry it copies out only exists in the fixture vault, so if
        `orient.FILES` were still pointed at the live checkout the uid would
        resolve to nothing and come back private.
        """
        root = self.studio()
        real = LIVE_STUDIO / "vault" / "files" / f"{REAL_ELIGIBLE_ENTRY}.md"
        self.assertPlanted(real.is_file(), f"real substrate {REAL_ELIGIBLE_ENTRY} is missing")
        shutil.copy2(real, root / "vault" / "files" / f"{REAL_ELIGIBLE_ENTRY}.md")
        classify = self.classifier_over(root)
        copied = frontmatter(root / "vault" / "files" / f"{REAL_ELIGIBLE_ENTRY}.md")
        self.assertPlanted(
            copied.get("extraction_scope") not in (None, "external"),
            "the copied entry was supposed to carry a non-external publishing "
            f"label; it carries {copied.get('extraction_scope')!r}",
        )

        self.assertEqual(
            classify(REAL_ELIGIBLE_ENTRY), orient.vp.OS_SEGMENT,
            msg="real agent-authored governed work was ruled ineligible to "
                "reach a model on the strength of a publishing label. Do NOT "
                "re-derive egress from extraction_scope.",
        )

        scopes = {
            "ship": "5c07e001",
            "argo-reference": "5c07e002",
            "internal": "5c07e003",
            "private": "5c07e004",
        }
        for scope, uid in scopes.items():
            with self.subTest(extraction_scope=scope):
                self.plant_entry(root, uid, f"extraction_scope: {scope}\ntype: note\n")
                self.assertEqual(
                    classify(uid), orient.vp.OS_SEGMENT,
                    msg=f"extraction_scope: {scope} was treated as an egress "
                        "decision. It is a publishing label.",
                )

    def test_an_ineligible_projection_is_still_readable_by_the_studio(self) -> None:
        """ADR-065: do not gate agent READ on a publishing label.

        Ineligible-for-egress is not the same as invisible. Agents have hands
        on an adopted folder — that is the whole point of the ATTACHED floor
        surviving adoption — so the governed entry has to stay readable on
        disk. A build that "protected" imported bodies by stripping or
        encrypting them would have built a boundary without naming a second
        party, and the model provider is not on the other side of this one.
        """
        root = self.studio()
        cloud = self.cloud_folder(files={"quarterly-plan.md": "# Q3\n\nreadable\n"})
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)

        projections = self.projections_in(root)
        self.assertPlanted(projections, "adoption produced no governed entries")
        for projection in projections:
            with self.subTest(projection=projection.name):
                self.assertTrue(os.access(projection, os.R_OK))
                self.assertTrue(projection.read_text(encoding="utf-8").strip())
        source = cloud / "quarterly-plan.md"
        self.assertTrue(os.access(source, os.R_OK))
        self.assertTrue(os.access(source, os.W_OK), msg="agents can modify an adopted folder")


# --------------------------------------------------------------------------- #
# Drift — the case with no prior art                                            #
# --------------------------------------------------------------------------- #

class DriftTests(FolderCase):
    """A cloud folder re-syncs, its path changes, and the mount must survive.

    The move these fixtures make is the one a re-sync makes: the leaf keeps its
    name, the parent is renamed beside itself, and the folder therefore stays
    inside the same grandparent. Nothing here asserts HOW the folder is
    re-found — that is the build lane's argument to make — only that it is, and
    that its `mount_uid` comes through unchanged.
    """

    def moved_fixture(self, *, adopt: bool):
        root = self.studio()
        cloud = self.cloud_folder(parent="sync/OneDrive - Acme", leaf="Marketing")
        record = folder.mount(root, cloud, name="Marketing")
        if adopt:
            folder.adopt(root, record.mount_uid)
        before = self.only_mount(root)

        moved = self._tmp / "sync" / "OneDrive - Acme (1)" / "Marketing"
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(cloud), str(moved))

        # Controls: the move is real, the content is the same folder's content,
        # and the registry is genuinely stale. Without all three, "reconcile
        # re-found it" could be satisfied by a folder that never moved.
        self.assertPlanted(not cloud.exists(), "the old path still exists; nothing moved")
        self.assertPlanted(moved.is_dir(), "the folder is not at the new path")
        self.assertPlanted(
            (moved / "quarterly-plan.md").is_file(),
            "the moved folder lost its contents, so it is not the same folder",
        )
        self.assertPlanted(
            Path(before.path).resolve() == cloud.resolve(),
            "the registry did not record the pre-move path, so reconcile has "
            "no stale state to repair and this case would prove nothing",
        )
        return root, before, moved

    def test_a_moved_attached_folder_is_refound_with_its_uid_intact(self) -> None:
        """Drift has to work in the state that wrote nothing into the folder.

        An ATTACHED mount left no marker behind — attach requires nothing — so
        this is the case that forces `fingerprint` to answer "is this the same
        folder somewhere else?" without help from anything on disk inside it.
        Solving drift only for ADOPTED folders would solve it for the state
        that did not need solving.
        """
        root, before, moved = self.moved_fixture(adopt=False)

        folder.reconcile(root)

        after = self.only_mount(root)
        self.assertEqual(
            after.mount_uid, before.mount_uid,
            msg="the mount_uid changed when the folder moved. A move must "
                "never look like an unmount plus a new mount.",
        )
        self.assertEqual(
            Path(after.path).resolve(), moved.resolve(),
            msg=f"reconcile left the mount pointing at a path that no longer "
                f"exists ({after.path})",
        )
        self.assertEqual(after.state, folder.STATE_ATTACHED)

    def test_a_moved_adopted_folder_is_refound_with_its_uid_intact(self) -> None:
        """The same property in the state where governed entries depend on it.

        Every governed entry created by adoption points at this mount. If the
        uid moves, they are all orphaned at once — and they are orphaned
        quietly, on a path nothing errors on, which is why this is the drift
        case the checkpoint ranks third among the gaps.
        """
        root, before, moved = self.moved_fixture(adopt=True)

        folder.reconcile(root)

        after = self.only_mount(root)
        self.assertEqual(after.mount_uid, before.mount_uid)
        self.assertEqual(Path(after.path).resolve(), moved.resolve())
        self.assertEqual(after.state, folder.STATE_ADOPTED)
        self.assertEqual(
            after.adopted_at, before.adopted_at,
            msg="the folder moved and the studio re-dated its adoption",
        )

    def test_a_move_is_never_an_unmount_plus_a_new_mount(self) -> None:
        """Stated negatively, because that is the shape the bug takes.

        The easy implementation of drift is "the path is gone, so drop the
        record; here is a folder I do not recognise, so mint one". It passes a
        casual read of `reconcile` and destroys every reference in the studio.
        So: one record before, one record after, the same uid, the same
        per-file uids, and nothing recycled.
        """
        root, before, moved = self.moved_fixture(adopt=True)
        file_uids_before = sorted(p.stem for p in self.projections_in(root))
        self.assertPlanted(file_uids_before, "the adopted fixture has no governed entries")

        folder.reconcile(root)

        records = folder.mounts(root)
        self.assertEqual(
            len(records), 1,
            msg=f"a moved folder produced {len(records)} mount records: "
                f"{[m.mount_uid for m in records]}. The old record was left "
                "behind as a ghost, or a new mount was minted, or both.",
        )
        self.assertEqual(records[0].mount_uid, before.mount_uid)
        self.assertEqual(
            sorted(p.stem for p in self.projections_in(root)), file_uids_before,
            msg="the per-file uids changed across a move; governed entries "
                "were re-minted rather than re-pointed",
        )
        recycle = root / "recycle"
        self.assertFalse(
            recycle.exists() and any(recycle.rglob("*.md")),
            msg="a move recycled governed substrate. Never hard-delete, and "
                "never soft-delete something that did not go away.",
        )

    def test_reconcile_repairs_the_projection_handles_that_a_move_breaks(self) -> None:
        """The known asymmetry, and the reason this build is worth doing twice.

        Sidecars find their file by relative path (`../<name>`), so they travel
        inside the folder and survive a whole-folder move for free. Vault
        projections store studio-relative `source_path` / `original_path`
        strings and break — that bug exists for in-tree moves today. The
        dangerous part is that after a move everything *looks* fine: the mount
        re-points, the sidecars still resolve, and only the governed entries
        the rest of the studio actually reads are pointing at nothing.

        This case will not run over a fixture that did not achieve the break.
        Before reconcile it requires the recorded handle to resolve to nothing;
        if it already resolved, the case proved nothing and says so.
        """
        root, before, moved = self.moved_fixture(adopt=True)
        projections = self.projections_in(root)
        self.assertPlanted(projections, "the adopted fixture has no governed entries")

        def handles(projection: Path):
            front = frontmatter(projection)
            return {
                key: resolve_recorded(
                    front.get(key), studio_root=root,
                    projection_dir=projection.parent,
                    mount_path=Path(self.only_mount(root).path),
                )
                for key in ("source_path", "original_path", "source_sidecar")
                if front.get(key)
            }

        broken = {p.name: handles(p) for p in projections}
        self.assertPlanted(
            any(broken.values()),
            "no projection recorded source_path, original_path or "
            "source_sidecar at all, so there is no handle to break or repair",
        )
        self.assertPlanted(
            all(target is None for entry in broken.values() for target in entry.values()),
            "a projection handle still resolved BEFORE reconcile, so the move "
            f"did not break what this case exists to fix: {broken}",
        )

        folder.reconcile(root)

        for projection in projections:
            with self.subTest(projection=projection.name):
                front = frontmatter(projection)
                repaired = handles(projection)
                self.assertTrue(
                    repaired,
                    msg=f"{projection.name} no longer records any handle to its "
                        "source; repairing a path is not deleting it",
                )
                for key, target in repaired.items():
                    self.assertIsNotNone(
                        target,
                        msg=f"{projection.name}'s {key} still points at nothing "
                            f"after reconcile ({front.get(key)!r}). The mount "
                            "was re-found and the governed entry was left "
                            "behind — this is the asymmetry the build exists "
                            "to close.",
                    )
                source = repaired.get("source_path")
                if source is not None and front.get("source_hash"):
                    self.assertEqual(
                        sha256_of(source), front.get("source_hash"),
                        msg=f"{projection.name}'s source_path now resolves to a "
                            "different file than the one it was derived from",
                    )

    def test_the_sidecars_travel_with_the_folder_and_are_not_rewritten(self) -> None:
        """The other half of the asymmetry: the side that already works.

        The sidecar's `../<name>` handle is correct before and after the move,
        so reconcile has nothing to do to it — and a reconcile that rewrites
        sidecars anyway is churning canonical substrate to fix a derived
        surface, which is invariant 8 inverted. Byte-comparison, because a
        re-stamped `modified:` is exactly that churn.
        """
        root, before, moved = self.moved_fixture(adopt=True)
        sidecars = {p.relative_to(moved).as_posix(): p.read_bytes()
                    for p in self.sidecars_in(moved)}
        self.assertPlanted(sidecars, "the adopted fixture has no sidecars to travel")
        for relative in sidecars:
            handle = frontmatter(moved / relative).get("source_path")
            self.assertPlanted(
                handle and (moved / relative).parent.joinpath(str(handle)).resolve().is_file(),
                f"{relative} did not resolve after the move, so this case is "
                "not about the side of the asymmetry that works",
            )

        folder.reconcile(root)

        after = {p.relative_to(moved).as_posix(): p.read_bytes()
                 for p in self.sidecars_in(moved)}
        self.assertEqual(
            sorted(after), sorted(sidecars),
            msg="reconcile added or removed sidecars in a folder that only moved",
        )
        for relative, body in sidecars.items():
            with self.subTest(sidecar=relative):
                self.assertEqual(
                    after[relative], body,
                    msg="reconcile rewrote a sidecar that was already correct",
                )

    def test_reconcile_over_a_folder_that_did_not_move_changes_nothing(self) -> None:
        """The no-op path, because a repair that always fires is not a repair.

        If reconcile re-mints, re-stamps or re-writes on a mount that is
        perfectly fine, then every drift case above passes for the wrong
        reason, and the studio churns its governed substrate every time
        somebody runs the tool.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        record = folder.mount(root, cloud, name="Marketing")
        folder.adopt(root, record.mount_uid)
        before = self.only_mount(root)
        vault_before = tree_digest(root / "vault" / "files")
        folder_before = tree_digest(cloud)
        self.assertPlanted(vault_before, "the adopted fixture has no governed entries")

        folder.reconcile(root)

        self.assertEqual(tree_digest(cloud), folder_before,
                         msg="reconcile touched a mounted folder that had not moved")
        self.assertEqual(tree_digest(root / "vault" / "files"), vault_before,
                         msg="reconcile rewrote governed entries that were correct")
        after = self.only_mount(root)
        # Bookkeeping the registry adds around the record (a last-checked
        # stamp, say) is the build lane's business; the record itself moving
        # under a mount that did not drift is not.
        for field in ("mount_uid", "name", "path", "state", "mounted_at",
                      "mounted_by", "adopted_at"):
            with self.subTest(field=field):
                self.assertEqual(
                    getattr(after, field), getattr(before, field),
                    msg=f"reconcile changed {field} on a mount that had not drifted",
                )

    def test_reconcile_reports_the_move_it_made(self) -> None:
        """A repair nobody can see is a repair nobody can audit.

        Deliberately the loosest case in this file: the surface names
        `ReconcileReport` and fixes none of its fields, so this asks only that
        the report, however it is shaped, mentions the mount it moved or where
        it moved to. If the build lane has a better shape, this is the case to
        argue with.
        """
        root, before, moved = self.moved_fixture(adopt=False)

        report = folder.reconcile(root)

        self.assertIsNotNone(report, msg="reconcile returned nothing at all")
        rendered = repr(report)
        try:
            rendered += json.dumps(report, default=str)
        except Exception:
            rendered += str(report)
        self.assertTrue(
            before.mount_uid in rendered or str(moved) in rendered,
            msg="the reconcile report names neither the mount it re-found nor "
                f"the path it found it at: {rendered[:400]}",
        )


# --------------------------------------------------------------------------- #
# The registry and the CLI                                                      #
# --------------------------------------------------------------------------- #

class RegistryTests(FolderCase):
    """Listing is a read. A read that writes is how a studio grows surprises."""

    def test_mounts_on_a_studio_with_no_registry_is_empty_and_writes_nothing(self) -> None:
        """Zero mounts is a legitimate state — it is every studio's day one.

        `compose.lock` does not exist in this Studio and never has: zero vault
        mounts, ever. A `mounts()` that raises on a missing registry, or that
        creates one to answer the question, makes the empty state cost
        something.
        """
        root = self.studio()
        registry = root / folder.MOUNT_REGISTRY_REL
        self.assertPlanted(not registry.exists(), "the fixture already has a registry")

        self.assertEqual(folder.mounts(root), [])
        self.assertFalse(registry.exists(), msg="mounts() created the registry it was reading")

    def test_the_registry_is_json_and_carries_every_uid(self) -> None:
        """Another process has to be able to read this, including a human.

        The frozen path ends in `.json`; this is the cheap check that it holds
        JSON rather than a pickle, a lockfile dialect, or JSONL. Two mounts,
        not one — a single-record JSONL file is also valid JSON, so a one-mount
        fixture cannot tell the two formats apart.
        """
        root = self.studio()
        first_folder = self.cloud_folder(leaf="Marketing")
        second_folder = self.cloud_folder(leaf="Finance")
        first = folder.mount(root, first_folder, name="Marketing")
        second = folder.mount(root, second_folder, name="Finance")
        self.assertPlanted(
            len(folder.mounts(root)) == 2, "the fixture should hold two mounts"
        )

        data = json.loads((root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8"))

        rendered = json.dumps(data)
        self.assertIn(first.mount_uid, rendered)
        self.assertIn(second.mount_uid, rendered)
        self.assertIn(str(first_folder.resolve()), rendered)
        self.assertIn(str(second_folder.resolve()), rendered)

    def test_two_concurrent_mounts_both_survive_registry_rmw(self) -> None:
        root = self.studio()
        clouds = (
            self.cloud_folder(parent="concurrent-a", leaf="Marketing"),
            self.cloud_folder(parent="concurrent-b", leaf="Finance"),
        )
        barrier = threading.Barrier(3)
        results = []
        failures = []

        def do_mount(cloud: Path, name: str) -> None:
            try:
                barrier.wait(timeout=5)
                results.append(folder.mount(root, cloud, name=name))
            except Exception as exc:  # surfaced in the parent assertion
                failures.append(exc)

        threads = [
            threading.Thread(target=do_mount, args=(clouds[0], "Marketing")),
            threading.Thread(target=do_mount, args=(clouds[1], "Finance")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(failures)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        stored = json.loads(
            (root / folder.MOUNT_REGISTRY_REL).read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(stored["mounts"]),
            {record.mount_uid for record in results},
        )
        self.assertEqual(len(stored["mounts"]), 2)

    def test_mounts_returns_foldermount_records(self) -> None:
        """`mounts(root) -> list[FolderMount]`, not a list of dicts.

        Every other case in this file reads `.mount_uid` and `.state` off what
        `mounts()` returns, so this is the one that fails clearly if the return
        type slipped.
        """
        root = self.studio()
        cloud = self.cloud_folder()
        folder.mount(root, cloud, name="Marketing")

        records = folder.mounts(root)

        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], folder.FolderMount)
        self.assertIn(records[0].state, folder.STATES)
        self.assertIsInstance(records[0].fingerprint, dict)

    def test_the_cli_list_on_a_studio_with_no_mounts_exits_zero(self) -> None:
        """`main(argv=None) -> int`, and `list` is the harmless one.

        Run against this live checkout on purpose: it has no folder mounts, and
        the live-studio guard in `tearDown` turns "list created a registry
        here" into a red. That is the cheapest possible proof that a read stays
        a read on a real studio.
        """
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = folder.main(["list"])

        self.assertEqual(code, 0, msg=f"`list` exited {code} on a studio with no mounts")


# --------------------------------------------------------------------------- #
# Prior art — the refusals this build removes                                   #
# --------------------------------------------------------------------------- #

class ImportWalkerPriorArtTests(FolderCase):
    """Why a new tool exists, pinned so it cannot silently stop being true.

    Every case in this file is written against the premise that the adoption
    machinery in `tropo-import-walker.py` cannot reach a folder outside the
    studio. If somebody removes that refusal, the premise moved and this suite
    should say so rather than keep testing a distinction that no longer exists.
    """

    def test_the_import_walker_still_refuses_a_source_outside_the_studio(self) -> None:
        """`create-sidecar` raises "Source file is not inside Studio root".

        This is the blocker the build removes, and it is checked against the
        real tool rather than quoted from the surface document.
        """
        self.assertPlanted(IMPORT_WALKER.is_file(), f"{IMPORT_WALKER} is missing")
        root = self.studio()
        # The walker refuses a root with no `.tropo/` before it ever looks at
        # the source, and a non-zero exit for THAT reason would let this case
        # pass while proving nothing about out-of-tree sources.
        (root / ".tropo").mkdir(exist_ok=True)
        outside = self.cloud_folder(parent="elsewhere/OneDrive - Acme", leaf="Personal")
        source = outside / "quarterly-plan.md"
        self.assertPlanted(source.is_file(), "the fixture source file is missing")

        completed = subprocess.run(
            [sys.executable, str(IMPORT_WALKER), "--studio-root", str(root),
             "create-sidecar", "--source", str(source)],
            capture_output=True, text=True,
        )
        output = completed.stdout + completed.stderr
        self.assertPlanted(
            "does not contain .tropo" not in output,
            f"the walker refused the fixture STUDIO, not the out-of-tree "
            f"source, so this case tested nothing: {output.strip()!r}",
        )

        self.assertNotEqual(
            completed.returncode, 0,
            msg="the import walker accepted an out-of-tree source. If that "
                "refusal was deliberately removed, re-read "
                "FOLDER-MOUNT-SURFACE.md: this suite assumes tropo-folder.py "
                "is the tool that reaches outside the studio.",
        )
        self.assertIn("not inside Studio root", output)
        self.assertFalse(
            (outside / SIDECAR_DIR).exists(),
            msg="the refusal still wrote into the folder it refused",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
