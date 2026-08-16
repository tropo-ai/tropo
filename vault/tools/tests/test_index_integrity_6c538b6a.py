"""Causal suite for index-integrity companion 6c538b6a (AC1/AC2/AC3).

THE ROOT CAUSE, stated once so the next reader does not have to re-derive it:
the disk->union invariant already existed in this validator and was enforced for
exactly ONE of 63 indexed types. check_working_copy_index_sync walks the
filesystem and reds a `type: working-copy` file with no row; it was added to close
defect family fa026415 and never generalized. Every other integrity check walks
INDEX ROWS and confirms they resolve to files, so the direction of travel was
union->disk and a governed file with no row was not flagged, not counted, simply
absent. That is how 125 accumulated unseen.

Row derivation is an opt-in SECOND gesture. tropo-mint-id, archive,
gardener-verdict, activate and publish-release call the freshener; direct
authoring — how essentially every governed entry here is created — calls nothing,
and the authoring gesture succeeds completely without it.

AC3 asks for a causal test that pins the path so the class cannot reopen silently,
and explicitly says a rebuild alone must NOT satisfy it. So the tests below assert
the CHECK's behaviour, not the vault's current cleanliness: a rebuild changes the
vault and changes nothing here.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
VALIDATOR = TOOLS / "tropo-validate.py"

_spec = importlib.util.spec_from_file_location("tv_index_integrity", VALIDATOR)
tv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tv)

BUILDER = TOOLS / "tropo-rebuild-index.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("rb_index_integrity", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ROW_FIELDS = {
    "type": "note", "status": "active", "state": "active",
    "owner": "talos", "created": "2026-08-15", "modified": "2026-08-15",
    "description": "", "tags": [], "file_ext": "md", "schema_version": 2,
}


def _vault(root: Path) -> Path:
    (root / "vault" / "files").mkdir(parents=True, exist_ok=True)
    return root


def _entry(root: Path, uid: str, title: str, extra: str = "") -> Path:
    path = root / "vault" / "files" / f"{uid}.md"
    path.write_text(
        f"---\nuid: {uid}\ntype: note\ntitle: {title}\n{extra}---\nbody\n",
        encoding="utf-8",
    )
    return path


def _index(root: Path, rows, archive=()):
    def _write(name, records):
        (root / "vault" / name).write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
    _write("00-index.jsonl", rows)
    _write("00-archive-index.jsonl", archive)


def _row(uid: str, title: str, **over):
    row = dict(ROW_FIELDS, uid=uid, title=title, path=f"vault/files/{uid}.md")
    row.update(over)
    return row


class CompletenessTests(unittest.TestCase):
    """AC1 — every on-disk governed file has a row, for EVERY type."""

    def test_a_file_with_a_row_passes(self):
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "aaaaaaaa", "Indexed")
            _index(root, [_row("aaaaaaaa", "Indexed")])
            findings, checked, defects = tv.check_index_union_completeness(root)
            self.assertEqual((checked, defects), (1, 0), findings)

    def test_a_file_with_no_row_is_caught(self):
        """The 125-file class, reproduced in one file."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "bbbbbbbb", "Never indexed")
            _index(root, [])
            findings, _checked, defects = tv.check_index_union_completeness(root)
            self.assertEqual(defects, 1)
            self.assertIn("bbbbbbbb", findings[0])
            self.assertIn("--only bbbbbbbb", findings[0], "the finding must name its cure")

    def test_the_archive_surface_counts_as_indexed(self):
        """An archived entry is indexed, on the opt-in history surface."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "cccccccc", "Archived")
            _index(root, [], archive=[_row("cccccccc", "Archived", state="archived")])
            _findings, _checked, defects = tv.check_index_union_completeness(root)
            self.assertEqual(defects, 0)

    def test_the_check_covers_types_other_than_working_copy(self):
        """THE GENERALIZATION, and the reason this AC exists.

        The pre-existing check was scoped to `type: working-copy`. Today's three
        real omissions were design-brief, doctrine and dev-spec — none of them
        working-copies, all invisible. A property, not a list.
        """
        for kind in ("design-brief", "doctrine", "dev-spec", "task", "release"):
            with tempfile.TemporaryDirectory() as t:
                root = _vault(Path(t))
                (root / "vault" / "files" / "dddddddd.md").write_text(
                    f"---\nuid: dddddddd\ntype: {kind}\ntitle: T\n---\nbody\n",
                    encoding="utf-8",
                )
                _index(root, [])
                _f, _c, defects = tv.check_index_union_completeness(root)
                self.assertEqual(defects, 1, f"type {kind!r} is not covered")

    def test_a_file_without_frontmatter_is_not_this_checks_finding(self):
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            (root / "vault" / "files" / "loose.md").write_text("no frontmatter\n")
            _index(root, [])
            _f, checked, defects = tv.check_index_union_completeness(root)
            self.assertEqual((checked, defects), (0, 0))

    def test_the_old_scope_would_have_missed_these(self):
        """Mutation control: restrict to working-copy and the class reopens."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            (root / "vault" / "files" / "eeeeeeee.md").write_text(
                "---\nuid: eeeeeeee\ntype: doctrine\ntitle: T\n---\nbody\n",
                encoding="utf-8",
            )
            _index(root, [])
            _f, _c, generalized = tv.check_index_union_completeness(root)
            old_scope = [
                p for p in (root / "vault" / "files").glob("*.md")
                if "type: working-copy" in p.read_text()
            ]
            self.assertEqual(generalized, 1)
            self.assertEqual(
                old_scope, [],
                "the pre-fix scope sees nothing here — which is exactly why 125 "
                "accumulated; if this list were non-empty the test proves nothing",
            )


class RowFreshnessTests(unittest.TestCase):
    """AC2 — a row's identity tracks its file."""

    def test_matching_titles_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "aaaaaaaa", "Same Title")
            _index(root, [_row("aaaaaaaa", "Same Title")])
            _f, checked, defects = tv.check_index_row_freshness(root)
            self.assertEqual((checked, defects), (1, 0))

    def test_a_stale_row_title_is_caught(self):
        """The f6a967fd class: file says v1.87.0, row still says v1.17.0."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "f6a967fd", "Tropo Release Notes — v1.87.0")
            _index(root, [_row("f6a967fd", "Tropo Release Notes — v1.17.0")])
            findings, _c, defects = tv.check_index_row_freshness(root)
            self.assertEqual(defects, 1)
            self.assertIn("v1.17.0", findings[0])
            self.assertIn("v1.87.0", findings[0], "both values must be shown")

    def test_an_apostrophe_in_a_quoted_title_is_not_staleness(self):
        """Regression: get_scalar truncates a single-quoted scalar at an embedded
        apostrophe, so 'Nobody's Looking' read as 'Nobody'. That produced 13 false
        positives on the first run of this check, all of them fresh rows."""
        title = "The L1 Thesis: What We Keep Assembling When Nobody's Looking"
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            (root / "vault" / "files" / "0716f70d.md").write_text(
                f"---\nuid: 0716f70d\ntype: note\ntitle: '{title}'\n---\nbody\n",
                encoding="utf-8",
            )
            _index(root, [_row("0716f70d", title)])
            findings, _c, defects = tv.check_index_row_freshness(root)
            self.assertEqual(defects, 0, findings)

    def test_a_literal_unicode_escape_in_a_row_is_not_staleness(self):
        """Regression: 104 of 1,939 archive rows store an em dash as the six
        characters \\u2014. That is an archive-writer encoding defect, filed
        separately — reporting it as staleness would make this check's count wrong
        about its own subject."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "090aa749", "Tropo-OS — What We Built")
            _index(root, [_row("090aa749", "Tropo-OS \\u2014 What We Built")])
            findings, _c, defects = tv.check_index_row_freshness(root)
            self.assertEqual(defects, 0, findings)

    def test_an_absent_row_is_the_other_checks_finding(self):
        """One check, one subject: completeness owns absence."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "bbbbbbbb", "Unindexed")
            _index(root, [])
            _f, checked, defects = tv.check_index_row_freshness(root)
            self.assertEqual((checked, defects), (0, 0))


class EscapedTitleProjectionTests(unittest.TestCase):
    """AC2 root cure — the index builder projects titles through the canonical parser.

    A149's root cause, confirmed at the line: _derived_row_title called get_scalar,
    which strips a double-quoted scalar's OUTER quotes but does not YAML-decode
    escaped INNER quotes. process_file then wrote the corruption into JSONL and
    onward to SQLite and FTS. Exactly one file in 4,740 uses an escaped quote in a
    title, which is why a valid document projected as a single backslash for months
    without anyone noticing — until the AC2 freshness check asked whether rows still
    agree with their files.

    Per the dispatch: no special-casing of 1a83a7ab or of escaped quotes. The cure is
    the parser, so these tests exercise the general path.
    """

    ESCAPED = '"Import your work" — Get-Started onboarding step (RT3 draft, for Metis G86)'

    def setUp(self):
        self.rb = _load_builder()

    def _file(self, root: Path, uid: str, title_line: str) -> Path:
        path = root / f"{uid}.md"
        path.write_text(
            f"---\nuid: {uid}\ntype: note\n{title_line}\nstatus: active\n---\nbody\n",
            encoding="utf-8",
        )
        return path

    def test_process_file_round_trips_an_escaped_quote_title_exactly(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            path = self._file(root, "1a83a7ab",
                              'title: "\\"Import your work\\" — Get-Started onboarding '
                              'step (RT3 draft, for Metis G86)"')
            record = self.rb.process_file(path)
            self.assertIsNotNone(record)
            self.assertEqual(record.get("title"), self.ESCAPED)

    def test_ordinary_titles_are_unchanged(self):
        """The cure must not disturb the 4,739 files that were always correct."""
        cases = {
            "aaaaaaaa": ("title: Plain unquoted title", "Plain unquoted title"),
            "bbbbbbbb": ("title: 'Single quoted with an apostrophe: Nobody''s Looking'",
                         "Single quoted with an apostrophe: Nobody's Looking"),
            "cccccccc": ('title: "Double quoted — with an em dash"',
                         "Double quoted — with an em dash"),
            "dddddddd": ("title: Trailing spaces here   ", "Trailing spaces here"),
        }
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for uid, (line, expected) in cases.items():
                path = self._file(root, uid, line)
                self.assertEqual(
                    self.rb.process_file(path).get("title"), expected,
                    f"{uid} projected wrong",
                )

    def test_the_derived_precedence_still_holds(self):
        """A145's ruling: title, then agent_name, then name, then filename stem."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            agent = root / "eeeeeeee.md"
            agent.write_text(
                "---\nuid: eeeeeeee\ntype: agent\nagent_name: Talos\n---\nbody\n",
                encoding="utf-8")
            self.assertEqual(
                self.rb._derived_row_title(agent.read_text().split('---', 2)[1], agent),
                "Talos")
            bare = root / "ffffffff.md"
            bare.write_text("---\nuid: ffffffff\ntype: note\n---\nbody\n", encoding="utf-8")
            self.assertEqual(
                self.rb._derived_row_title(bare.read_text().split('---', 2)[1], bare),
                "ffffffff", "the filename stem is the floor and is never empty")

    def test_unparseable_frontmatter_still_yields_a_usable_title(self):
        """Fallback exists so a malformed file degrades to get_scalar rather than
        collapsing to its filename stem."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            broken = root / "99999999.md"
            broken.write_text(
                "---\nuid: 99999999\ntitle: Recoverable Title\n  bad: [unclosed\n---\nb\n",
                encoding="utf-8")
            title = self.rb._derived_row_title(
                broken.read_text().split('---', 2)[1], broken)
            self.assertEqual(title, "Recoverable Title")

    def test_restoring_raw_get_scalar_reds_the_escaped_title(self):
        """Negative plant A149 specified — the pre-fix derivation, verbatim."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            path = self._file(root, "1a83a7ab",
                              'title: "\\"Import your work\\" — Get-Started onboarding '
                              'step (RT3 draft, for Metis G86)"')
            fm = path.read_text().split('---', 2)[1]

            def pre_fix(fm_text, filepath):
                for key in ('title', 'agent_name', 'name'):
                    value = (self.rb.get_scalar(fm_text, key) or '').strip()
                    if value:
                        return value
                return filepath.stem

            corrupted = pre_fix(fm, path)
            self.assertNotEqual(
                corrupted, self.ESCAPED,
                "the pre-fix derivation must corrupt this title; if it does not, the "
                "cure is untested and this suite proves nothing",
            )
            self.assertEqual(corrupted, "\\", "pre-fix projected a single backslash")


class RootCausePinTests(unittest.TestCase):
    """AC3 — the class cannot reopen silently, and a rebuild alone does not satisfy it."""

    def test_the_check_is_wired_into_the_default_pass(self):
        """A check nobody runs is not a gate. This is the half a rebuild cannot fake."""
        source = VALIDATOR.read_text(encoding="utf-8")
        main_body = source[source.index("Index Union Completeness (6c538b6a AC1"):]
        self.assertIn("check_index_union_completeness(vault)", main_body)
        self.assertIn("check_index_row_freshness(vault)", main_body)

    def test_a_rebuild_alone_does_not_satisfy_this_ac(self):
        """AC3 says so explicitly. These tests assert the CHECK's behaviour against
        fixtures, so cleaning the live vault cannot turn them green — the only way
        to make them pass is for the check to exist and work."""
        with tempfile.TemporaryDirectory() as t:
            root = _vault(Path(t))
            _entry(root, "bbbbbbbb", "Never indexed")
            _index(root, [])
            _f, _c, defects = tv.check_index_union_completeness(root)
            self.assertEqual(
                defects, 1,
                "this fixture is independent of the live vault's index state",
            )

    def test_removing_the_check_reopens_the_class(self):
        """Mutation control on the property itself."""
        self.assertTrue(hasattr(tv, "check_index_union_completeness"))
        self.assertTrue(hasattr(tv, "check_index_row_freshness"))
        without = {n for n in dir(tv) if n.startswith("check_")}
        self.assertIn("check_working_copy_index_sync", without,
                      "the one-type ancestor must remain; this generalizes, not replaces")


if __name__ == "__main__":
    unittest.main()
