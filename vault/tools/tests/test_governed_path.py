#!/usr/bin/env python3
"""Governed filename slugging and index-free UID resolution (dev-spec 74f85939).

Every behavioural case lives in `fixtures/governed-path-vectors.json`, which the
TypeScript adapter executes too. Neither implementation is the other's oracle;
both answer to the vectors. Cases added here that are not in the vectors would
be Python-only behaviour, which is exactly the drift the shared file exists to
prevent — so the vector-driven tests below assert the file's contents rather
than restating them.

The mutation tests are the governing proof, per the spec's Acceptance section:
each fallback / index-independence / anchoring mutation must make a named test
fail. They are written as adversarial plants over a throwaway Studio root and
never touch the live Vault.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
VECTORS = TOOLS / "tests" / "fixtures" / "governed-path-vectors.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gp = _load("governed_path_under_test", TOOLS / "lib" / "governed_path.py")


def _vectors() -> dict:
    return json.loads(VECTORS.read_text(encoding="utf-8"))


class SharedVectorFileTests(unittest.TestCase):
    """The contract file itself, before anything that reads it."""

    def test_the_vector_file_exists_and_declares_all_three_sections(self) -> None:
        data = _vectors()
        for section in ("slug_from_title", "governed_filename", "resolve"):
            self.assertIn(section, data, f"vectors are missing {section}")
            self.assertTrue(data[section], f"{section} is empty")

    def test_every_case_is_named_so_a_failure_says_which_one(self) -> None:
        data = _vectors()
        for section in ("slug_from_title", "governed_filename", "resolve"):
            for case in data[section]:
                self.assertIn("name", case, f"unnamed case in {section}: {case}")


class SlugVectorTests(unittest.TestCase):
    def test_slug_matches_every_shared_vector(self) -> None:
        for case in _vectors()["slug_from_title"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    gp.slug_from_title(case["title"]), case["slug"],
                    f"slug vector {case['name']!r} disagrees with the shared contract")

    def test_slug_never_exceeds_sixty_characters(self) -> None:
        """Asserted as a property, not only through the truncation cases."""
        for case in _vectors()["slug_from_title"]:
            slug = gp.slug_from_title(case["title"])
            if slug is not None:
                with self.subTest(case=case["name"]):
                    self.assertLessEqual(len(slug), 60)

    def test_slug_output_is_always_in_the_permitted_alphabet(self) -> None:
        import re
        allowed = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
        for case in _vectors()["slug_from_title"]:
            slug = gp.slug_from_title(case["title"])
            if slug is not None:
                with self.subTest(case=case["name"]):
                    self.assertRegex(slug, allowed)


class GovernedFilenameVectorTests(unittest.TestCase):
    def test_filename_matches_every_shared_vector(self) -> None:
        for case in _vectors()["governed_filename"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    gp.governed_filename(case["uid"], case["title"]),
                    case["filename"])

    def test_the_uid_is_always_the_anchored_suffix(self) -> None:
        """Identity lives in the suffix. A slug is decoration in front of it."""
        for case in _vectors()["governed_filename"]:
            with self.subTest(case=case["name"]):
                name = gp.governed_filename(case["uid"], case["title"])
                self.assertTrue(
                    name == f"{case['uid']}.md"
                    or name.endswith(f"-{case['uid']}.md"),
                    f"{name} does not carry {case['uid']} as an anchored suffix")


class _Studio:
    """A throwaway Studio root. The live Vault is never touched."""

    def __init__(self, files: dict):
        self._tmp = tempfile.TemporaryDirectory(prefix="governed-path-")
        self.root = Path(self._tmp.name).resolve()
        for rel, content in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def close(self) -> None:
        self._tmp.cleanup()


class FilenameGuardVectorTests(unittest.TestCase):
    """P0-1: the UID gate applies to the WRITER entry point too.

    `governed_filename` had no validator, so a traversal-shaped uid produced
    `../../secret.md` and a writer would have created it there.
    """

    def test_filename_guards_match_every_shared_vector(self) -> None:
        for case in _vectors()["filename_guards"]:
            with self.subTest(case=case["name"]):
                if case["raises"] == "UNSAFE":
                    with self.assertRaises(gp.UnsafeGovernedPath):
                        gp.governed_filename(case["uid"], "Some Title")
                else:
                    gp.governed_filename(case["uid"], "Some Title")

    def test_a_traversal_uid_never_yields_a_traversal_filename(self) -> None:
        for bad in ("../../secret", "a/b", "..", "./x"):
            with self.subTest(uid=bad):
                with self.assertRaises(gp.UnsafeGovernedPath):
                    gp.governed_filename(bad, None)


class HomeEscapeTests(unittest.TestCase):
    """P0-2 second half: a governed HOME that is itself a symlink outward.

    Candidate-under-home passes trivially when the home escaped, so the home is
    canonicalized and required to stay under the real Studio root.
    """

    def test_a_home_symlinked_outside_the_studio_is_not_searched(self) -> None:
        studio = _Studio({"vault/agents/keep.md": "x\n"})
        self.addCleanup(studio.close)
        outside = studio.root.parent / f"outside-{studio.root.name}"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "secret-jj000001.md").write_text(
            "---\nuid: jj000001\n---\nsecret\n", encoding="utf-8")
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        files_home = studio.root / "vault" / "files"
        try:
            files_home.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this filesystem")
        self.assertIsNone(
            gp.resolve_governed_path("jj000001", studio.root),
            "vault/files pointed outside the Studio and was searched anyway — "
            "every candidate under an escaped home passes containment while "
            "every byte returned is outside")


class HomeIsALocationNotAPointerTests(unittest.TestCase):
    """A declared home that is a symlink to ANOTHER home inside the Studio.

    "Under the root" is not enough: `vault/files -> vault/agents` resolves
    inside the Studio and passes every containment check, while every agent
    record is served as a `vault/files` candidate and two homes silently
    become one. (Argus A145 third review.)
    """

    def test_a_home_symlinked_to_another_home_inside_the_studio_is_refused(self) -> None:
        studio = _Studio({
            "vault/agents/talos-ll000001.md": "---\nuid: ll000001\n---\nagent record\n",
        })
        self.addCleanup(studio.close)
        files_home = studio.root / "vault" / "files"
        try:
            files_home.symlink_to(studio.root / "vault" / "agents",
                                  target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this filesystem")

        found = gp.resolve_governed_path("ll000001", studio.root, home="vault/files")
        self.assertIsNone(
            found,
            "vault/files was a symlink to vault/agents and served an agent "
            "record as a files candidate — a governed home is a location, not "
            "a pointer to one")

    def test_the_real_home_still_resolves_the_control(self) -> None:
        studio = _Studio({
            "vault/agents/talos-ll000002.md": "---\nuid: ll000002\n---\nx\n",
        })
        self.addCleanup(studio.close)
        self.assertIsNotNone(
            gp.resolve_governed_path("ll000002", studio.root, home="vault/agents"),
            "control: a real, unsymlinked home must still resolve")


class FlagVectorTests(unittest.TestCase):
    def test_flag_matches_every_shared_vector(self) -> None:
        for case in _vectors()["flag"]:
            with self.subTest(case=case["name"]):
                files = {} if case["content"] is None else {gp.FLAG_PATH: case["content"]}
                studio = _Studio(files)
                self.addCleanup(studio.close)
                self.assertEqual(
                    gp.readable_minting_enabled(studio.root), case["enabled"],
                    f"flag vector {case['name']!r} disagrees with the shared contract")


class GuardVectorTests(unittest.TestCase):
    """Path containment (P0-2, Argus A145 review).

    Platform routes pass user-controlled identifiers into this resolver. Without
    UID-shape validation and a governed-home allowlist that is a local-file
    -disclosure surface, not a resolver.
    """

    def test_guards_match_every_shared_vector(self) -> None:
        studio = _Studio({"vault/files/aa000001.md": "---\nuid: aa000001\n---\nb\n"})
        self.addCleanup(studio.close)
        for case in _vectors()["guards"]:
            with self.subTest(case=case["name"]):
                kwargs = {"home": case["home"]} if case.get("home") else {}
                if case["raises"] == "UNSAFE":
                    with self.assertRaises(gp.UnsafeGovernedPath):
                        gp.resolve_governed_path(case["uid"], studio.root, **kwargs)
                else:
                    gp.resolve_governed_path(case["uid"], studio.root, **kwargs)

    def test_a_symlink_escaping_the_home_is_not_followed(self) -> None:
        """A file inside the home whose real path is outside it.

        Containment is checked on the RESOLVED path for exactly this: the
        directory listing looks entirely normal, and the bytes returned would
        be someone else's.
        """
        studio = _Studio({"outside/secret-hh000001.md": "---\nuid: hh000001\n---\nsecret\n"})
        self.addCleanup(studio.close)
        (studio.root / "vault" / "files").mkdir(parents=True, exist_ok=True)
        link = studio.root / "vault" / "files" / "innocent-hh000001.md"
        try:
            link.symlink_to(studio.root / "outside" / "secret-hh000001.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this filesystem")
        self.assertIsNone(
            gp.resolve_governed_path("hh000001", studio.root),
            "a symlink out of the governed home was followed — the listing "
            "looks normal and the bytes belong to someone else")

    def test_an_absolute_literal_outside_the_homes_is_refused(self) -> None:
        studio = _Studio({"outside/secret-hh000002.md": "---\nuid: hh000002\n---\nx\n"})
        self.addCleanup(studio.close)
        self.assertIsNone(
            gp.resolve_governed_path(
                "hh000002", studio.root,
                literal=studio.root / "outside" / "secret-hh000002.md"),
            "an absolute literal outside every governed home was read")


class FeatureFlagTests(unittest.TestCase):
    """Fail-closed, and only writers ever ask."""

    def _flag(self, content: str | None):
        files = {} if content is None else {gp.FLAG_PATH: content}
        studio = _Studio(files)
        self.addCleanup(studio.close)
        return gp.readable_minting_enabled(studio.root)

    def test_missing_malformed_and_wrong_typed_flags_all_read_false(self) -> None:
        for label, content in [
            ("missing", None),
            ("empty", ""),
            ("malformed json", "{not json"),
            ("json but not an object", "[]"),
            ("enabled as a string", '{"enabled": "true"}'),
            ("enabled as 1", '{"enabled": 1}'),
            ("no enabled key", '{"schema_version": 1}'),
        ]:
            with self.subTest(flag=label):
                self.assertFalse(self._flag(content), f"{label} must read false")

    def test_only_a_real_boolean_true_enables(self) -> None:
        self.assertTrue(self._flag('{"enabled": true, "schema_version": 1}'))

    def test_the_live_studio_flag_is_false_in_phase_one(self) -> None:
        root = TOOLS.parents[1]
        self.assertFalse(
            gp.readable_minting_enabled(root),
            "Phase 1 must ship with minting disabled; Phase 2 is the isolated flip")


class ResolveVectorTests(unittest.TestCase):
    def test_resolution_matches_every_shared_vector(self) -> None:
        for case in _vectors()["resolve"]:
            with self.subTest(case=case["name"]):
                studio = _Studio(case["files"])
                self.addCleanup(studio.close)
                kwargs = {}
                if case.get("home"):
                    kwargs["home"] = case["home"]
                if case.get("literal"):
                    kwargs["literal"] = studio.root / case["literal"]
                if case.get("literal_absolute_outside"):
                    kwargs["literal"] = studio.root / case["literal_absolute_outside"]

                if case["expect"] == "AMBIGUOUS":
                    with self.assertRaises(Exception, msg=(
                        "two files claiming one uid must fail LOUDLY — picking "
                        "one silently is how the wrong body gets indexed")):
                        gp.resolve_governed_path(case["uid"], studio.root, **kwargs)
                    continue

                got = gp.resolve_governed_path(case["uid"], studio.root, **kwargs)
                if case["expect"] is None:
                    self.assertIsNone(got)
                else:
                    self.assertIsNotNone(
                        got, f"expected {case['expect']}, resolved nothing")
                    self.assertEqual(
                        Path(got).resolve(),
                        (studio.root / case["expect"]).resolve())


class IndexIndependenceTests(unittest.TestCase):
    """AC5 / AC10. The reason this resolver exists at all.

    This studio's index froze for hours on 2026-08-07. If opening a governed
    file had required the index, there would have been no vault to repair it
    with. Resolution is a directory scan and must stay one.
    """

    def test_resolution_works_with_no_index_present_at_all(self) -> None:
        studio = _Studio({
            "vault/files/readable-cc000001.md": "---\nuid: cc000001\n---\nbody\n",
        })
        self.addCleanup(studio.close)
        self.assertFalse((studio.root / "vault" / "00-index.jsonl").exists())
        got = gp.resolve_governed_path("cc000001", studio.root)
        self.assertEqual(
            Path(got).name, "readable-cc000001.md",
            "resolution must not need the index — that is the whole contract")

    def test_resolution_survives_a_deliberately_corrupt_index(self) -> None:
        studio = _Studio({
            "vault/files/readable-cc000002.md": "---\nuid: cc000002\n---\nbody\n",
            "vault/00-index.jsonl": "{ this is not json at all\n",
        })
        self.addCleanup(studio.close)
        got = gp.resolve_governed_path("cc000002", studio.root)
        self.assertIsNotNone(got, "a corrupt index must be irrelevant, not fatal")

    def test_the_library_does_not_import_any_index_module(self) -> None:
        """The mechanism assertion behind the two behavioural tests above.

        Both would still pass on an implementation that imported the index and
        merely happened not to need it in the fixture. Mutation AC10 re-adds
        the import; this is what catches it.
        """
        source = (TOOLS / "lib" / "governed_path.py").read_text(encoding="utf-8")
        for forbidden in ("index_surfaces", "00-index", "sqlite3",
                          "tropo-rebuild-index", "rebuild_index"):
            self.assertNotIn(
                forbidden, source,
                f"governed_path.py references {forbidden!r}. Resolution must be "
                f"a directory scan: the index is exactly the thing that is "
                f"unavailable when you most need to open a file (254a360b)")


class AnchoringTests(unittest.TestCase):
    """The negative half. An unanchored glob is the subtle way this breaks."""

    def test_a_longer_stem_ending_in_the_uid_is_not_a_match(self) -> None:
        studio = _Studio({
            "vault/files/xxxxdd000001.md": "---\nuid: xxxxdd000001\n---\nbody\n",
        })
        self.addCleanup(studio.close)
        self.assertIsNone(
            gp.resolve_governed_path("dd000001", studio.root),
            "'*<uid>.md' matched where only '<uid>.md' or '*-<uid>.md' may. "
            "That silently binds one record to another record's file")

    def test_the_hyphen_before_the_uid_is_required(self) -> None:
        studio = _Studio({
            "vault/files/reportdd000002.md": "---\nuid: reportdd000002\n---\nb\n",
        })
        self.addCleanup(studio.close)
        self.assertIsNone(gp.resolve_governed_path("dd000002", studio.root))

    def test_anchoring_rejects_even_when_the_frontmatter_agrees(self) -> None:
        """The only test that can actually see the anchor, and it exists
        because the first version of this suite could not.

        Every other negative here is refused twice over — by the missing hyphen
        AND by a frontmatter UID that does not match. So the unanchored-glob
        mutant passed all thirteen of them: the frontmatter check caught the
        file that the anchor should have. A plant that green-lights the mutant
        is measuring something other than what its name claims.

        This file's frontmatter DOES declare the uid, so the frontmatter check
        cannot reject it. Only the required hyphen can. Drop the anchor from
        `suffix` and this is the test that goes red.
        """
        studio = _Studio({
            "vault/files/xxxxdd000003.md": "---\nuid: dd000003\n---\nbody\n",
        })
        self.addCleanup(studio.close)
        self.assertIsNone(
            gp.resolve_governed_path("dd000003", studio.root),
            "'xxxx<uid>.md' resolved for <uid>. The convention is '<uid>.md' or "
            "'<slug>-<uid>.md'; an unanchored glob binds arbitrary filenames to "
            "a UID and the collision is silent")


# --------------------------------------------------------------------------
# CLI modes locked by the spec's acceptance criteria (AC9-AC12).
#
# They live in the test file rather than a tool because they ARE the
# acceptance runner: AC10's mutation check must prove each plant actually
# applied before trusting that it failed, and AC9's forward-only check must
# read the real diff rather than a summary of it.
# --------------------------------------------------------------------------

LIB = TOOLS / "lib" / "governed_path.py"
TS_LIB = TOOLS.parents[1] / "tropo-app" / "lib" / "governed-path.ts"

#: Each plant is (label, file, find, replace). A mutation that does not change
#: the file is reported as NOT APPLIED and fails the run — a plant that never
#: landed proves nothing, and a green result from one is worse than no result.
_MUTATIONS = [
    ("fallback removed — only the literal path is tried", LIB,
     'suffix = f"-{uid}.md"', 'suffix = f"-{uid}.md.disabled"'),
    ("index dependency introduced (AC10)", LIB,
     "import json\nimport re", "import json\nimport re\nimport sqlite3"),
    ("suffix glob widened past the hyphen anchor", LIB,
     'suffix = f"-{uid}.md"', 'suffix = f"{uid}.md"'),
    ("exact match skips frontmatter verification (P0-1)", LIB,
     "            if _frontmatter_uid(candidate) != uid:\n                continue",
     "            if False:\n                continue"),
    ("closed-frontmatter requirement dropped", LIB,
     '    return None  # never closed: a truncated file, not frontmatter',
     """    match = re.search(r"^uid:\\s*['\\"]?([^'\\"\\s]+)", "\\n".join(body), re.MULTILINE)
    return match.group(1) if match else None"""),
    ("uid shape validation removed (P0-2)", LIB,
     "    if not uid or len(uid) > _UID_MAX or not _UID_OK.match(uid):",
     "    if False:"),
    ("home allowlist removed (P0-2)", LIB,
     "        if home not in GOVERNED_HOMES:", "        if False:"),
    ("containment check removed (P0-2)", LIB,
     "            if not _contained(candidate, directory):\n                continue",
     "            if False:\n                continue"),
    ("ambiguity resolved silently instead of raising", LIB,
     "    if len(found) > 1:", "    if False:"),
    ("60-character truncation removed", LIB,
     "    if len(slug) > SLUG_MAX:", "    if False:"),
    ("explicit whitespace class swapped for native \\s", LIB,
     '_WS = r"[ \\t\\n\\r\\f\\v\\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"',
     '_WS = r"\\s"'),
    ("feature flag reads open instead of closed", LIB,
     "    except (OSError, ValueError):\n        return False",
     "    except (OSError, ValueError):\n        return True"),
    ("flag accepts a boolean schema_version (bool==1 divergence)", LIB,
     "    if isinstance(schema, bool) or not isinstance(schema, (int, float)):\n        return False",
     "    if False:\n        return False"),
    ("home may be a symlink as long as it lands under root", LIB,
     "        if real_home != real_root / rel:",
     "        if real_home != real_root and real_root not in real_home.parents:"),
    ("writer entry point loses its uid gate (P0-1)", LIB,
     "    _validate_uid(uid)\n    slug = slug_from_title(title)",
     "    slug = slug_from_title(title)"),
    ("home filtering removed entirely (P0-2)", LIB,
     "        if real_home != real_root / rel:\n            continue",
     "        if False:\n            continue"),
    ("literal short-circuits collision detection again", LIB,
     "            real = _canonical(candidate)\n            if real is not None:\n                found.append(real)",
     "            real = _canonical(candidate)\n            if real is not None:\n                return real"),
    ("literal containment check removed", LIB,
     "                and any(_contained(candidate, hp) for _, hp in homes)):",
     "                and True):"),
    ("frontmatter fence accepts a non-delimiter opening line", LIB,
     'if not lines or lines[0].rstrip("\\r") != "---":',
     'if not lines or not lines[0].startswith("---"):'),
]

#: The TypeScript adapter is mutated too. A mutation set that only exercises
#: one of two implementations proves the contract for one language and asserts
#: it for the other — which is exactly the gap the shared vectors exist to
#: close. (Argus A145 review.)
_TS_MUTATIONS = [
    ("ts: suffix glob widened past the hyphen anchor", TS_LIB,
     "const suffix = `-${uid}.md`;", "const suffix = `${uid}.md`;"),
    ("ts: writer entry point loses its uid gate", TS_LIB,
     "  validateUid(uid);\n  const slug = slugFromTitle(title);",
     "  const slug = slugFromTitle(title);"),
    ("ts: home filtering removed entirely", TS_LIB,
     "    .filter(({ rel, dir }) => canonical(dir) === path.join(root, rel))",
     "    .filter(() => true)"),
    ("ts: flag ignores schema_version", TS_LIB,
     "      raw.enabled === true &&\n      raw.schema_version === 1",
     "      raw.enabled === true"),
    ("ts: home may be a symlink as long as it lands under root", TS_LIB,
     "    .filter(({ rel, dir }) => canonical(dir) === path.join(root, rel))",
     "    .filter(({ dir }) => { const rh = canonical(dir); return rh !== null && (rh === root || rh.startsWith(root + path.sep)); })"),
    ("ts: frontmatter fence accepts a non-delimiter opening line", TS_LIB,
     'if (lines.length === 0 || lines[0].replace(/\\r$/, "") !== "---") return null;',
     'if (lines.length === 0 || !lines[0].startsWith("---")) return null;'),
    ("ts: literal containment check removed", TS_LIB,
     "      homes.some((dir) => contained(candidate, dir))", "      true"),
]


def _run_suite() -> bool:
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(TOOLS / "tests"),
         "-p", "test_governed_path.py", "-t", str(TOOLS.parents[1])],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def _run_ts_suite() -> bool:
    import subprocess
    app = TOOLS.parents[1] / "tropo-app"
    proc = subprocess.run(
        ["npx", "tsx", "tests/governed-path-vectors.ts"],
        capture_output=True, text=True, cwd=str(app),
    )
    return proc.returncode == 0


def _mutation_check() -> int:
    """AC10 — prove each plant applies, then require it to fail its suite."""
    originals = {LIB: LIB.read_text(encoding="utf-8"),
                 TS_LIB: TS_LIB.read_text(encoding="utf-8")}
    plants = [(m, _run_suite) for m in _MUTATIONS] + \
             [(m, _run_ts_suite) for m in _TS_MUTATIONS]
    failures = []
    print(f"mutation check: {len(plants)} plants "
          f"({len(_MUTATIONS)} python, {len(_TS_MUTATIONS)} typescript)\n")
    try:
        for (label, target, find, replace), runner in plants:
            source = originals[target]
            if find not in source:
                failures.append(f"NOT APPLIED (anchor missing): {label}")
                print(f"  [ANCHOR GONE] {label}")
                continue
            mutated = source.replace(find, replace, 1)
            if mutated == source:
                failures.append(f"NOT APPLIED (no change): {label}")
                print(f"  [NO CHANGE  ] {label}")
                continue
            target.write_text(mutated, encoding="utf-8")
            try:
                survived = runner()
            finally:
                target.write_text(source, encoding="utf-8")
            if survived:
                failures.append(f"SURVIVED: {label}")
                print(f"  [SURVIVED   ] {label}")
            else:
                print(f"  [caught     ] {label}")
    finally:
        for target, source in originals.items():
            target.write_text(source, encoding="utf-8")

    if not _run_suite():
        failures.append("the python suite is not green after restoring every mutation")
    if not _run_ts_suite():
        failures.append("the typescript suite is not green after restoring every mutation")
    print()
    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        print("\nA surviving mutation means the guard it removes is untested. A "
              "plant that did not apply means the check measured nothing.")
        return 1
    print(f"all {len(plants)} mutations applied and were caught in both "
          f"languages; both suites green after restore")
    return 0


def _assert_forward_only(base_ref: str) -> int:
    """AC9 — nothing existing is renamed or rewritten by this build."""
    import subprocess
    allowed_prefixes = (
        "vault/tools/lib/governed_path.py",
        "vault/tools/tests/test_governed_path.py",
        "vault/tools/tests/fixtures/governed-path-vectors.json",
        "tropo-app/lib/governed-path.ts",
        "tropo-app/tests/governed-path-vectors.ts",
        "tropo-app/tests/test-qa.ts",
        ".tropo-studio/readable-filenames.json",
        "vault/files/74f85939.md",
    )
    governed_homes = tuple(f"{h}/" for h in gp.GOVERNED_HOMES)
    proc = subprocess.run(
        ["git", "diff", "--name-status", "-M", base_ref, "HEAD"],
        capture_output=True, text=True, cwd=str(TOOLS.parents[1]),
    )
    if proc.returncode != 0:
        print(f"FAIL: cannot diff against {base_ref}: {proc.stderr.strip()}")
        return 1
    problems = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        if status.startswith(("R", "C")):
            if any(p.startswith(governed_homes) for p in paths):
                problems.append(f"{status}: {' -> '.join(paths)} (governed file moved)")
            continue
        for path_ in paths:
            if path_.startswith(governed_homes) and not path_.startswith(allowed_prefixes):
                problems.append(f"{status}: {path_} (pre-existing governed content edited)")
    if problems:
        print("FAIL: this build is forward-only; these are not:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"forward-only: no governed rename and no out-of-scope governed edit since {base_ref}")
    return 0


def _phase(name: str) -> int:
    """AC11/AC12 — the observable difference the flag makes, and nothing else."""
    root = TOOLS.parents[1]
    enabled = gp.readable_minting_enabled(root)
    if name == "resolver-only":
        if enabled:
            print("FAIL: phase resolver-only requires readable minting DISABLED; "
                  "the live flag is true")
            return 1
        print("phase resolver-only: flag false, writers still emit <uid>.md, "
              "both shapes resolve")
        return 0 if _run_suite() else 1
    if name == "mint-enabled":
        # Asserted on a throwaway root, and on the BASENAME a writer would
        # actually choose — not merely on the flag's value. Reading the flag
        # correctly and still minting the wrong name is the failure this is
        # for. (Argus A145 review.)
        studio = _Studio({
            gp.FLAG_PATH: '{"enabled": true, "schema_version": 1}',
            "vault/files/keep-b7c2d491.md": "---\nuid: b7c2d491\n---\nx\n",
        })
        try:
            before = sorted(p.name for p in (studio.root / "vault" / "files").iterdir())
            got = gp.mint_basename("b7c2d491", "Weekly Status Update", studio.root)
            if got != "weekly-status-update-b7c2d491.md":
                print(f"FAIL: enabled:true minted {got!r}, not the readable shape")
                return 1
            if gp.mint_basename("b7c2d491", "!!!", studio.root) != "b7c2d491.md":
                print("FAIL: an unusable title must still degrade to the bare shape")
                return 1
            (studio.root / gp.FLAG_PATH).write_text(
                '{"enabled": false, "schema_version": 1}', encoding="utf-8")
            got = gp.mint_basename("b7c2d491", "Weekly Status Update", studio.root)
            if got != "b7c2d491.md":
                print(f"FAIL: disabling the flag left minting at {got!r}")
                return 1
            after = sorted(p.name for p in (studio.root / "vault" / "files").iterdir())
            if before != after:
                print(f"FAIL: an existing file moved: {before} -> {after}")
                return 1
        finally:
            studio.close()
        print("phase mint-enabled: enabled:true mints readable, false restores bare, "
              "no existing file moves")
        return 0
    print(f"FAIL: unknown phase {name!r}")
    return 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--mutation-check" in argv:
        sys.exit(_mutation_check())
    if "--assert-forward-only" in argv:
        base = argv[argv.index("--base-ref") + 1] if "--base-ref" in argv else "origin/main"
        sys.exit(_assert_forward_only(base))
    if "--phase" in argv:
        sys.exit(_phase(argv[argv.index("--phase") + 1]))
    unittest.main(verbosity=1)
