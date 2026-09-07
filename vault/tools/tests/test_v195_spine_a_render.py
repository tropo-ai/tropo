"""v1.95 Spine A AC8 (f015de6b3a18) — the Studio Map ships as a HUMAN surface.

Mike, 2026-09-05: "Po rendered an html version of the tropo-studio-map, which
was nice, but it does not have any visual representation of the studio. I think
this is a missed opportunity." And: "on these shipped HTML artifacts, it's a
perfect location to put links to resources that would be valuable."

So this file pins the four things the render gained and the one thing it must
never do quietly:

  (a) the visual is GENERATED — nine labeled subsystem boxes, read from the
      index at render time, not written down in the generator;
  (b) --box carries no path from the building machine and no customer studio;
  (c) --overlay names this studio's own agents;
  (d) staleness covers EVERY input: the pass/fail/pass pair around an edit to
      the resources file, which the old Map-only fingerprint could not see;
  (e) a missing resources file REFUSES and names the file — the failure mode
      Mike's ask has is a Resources section that silently isn't there.

Fixtures are temp studios built from THIS studio's real Map, real index, and
real resources file, so (d) can mutate the resources file without touching the
governed original. (a) runs against the studio itself, because "render on this
studio" is the criterion's own wording and the artifact it leaves behind is
the fresh render the criterion wants anyway.

Wave 2 (f0151b4347af) — the render grew five DERIVED sections (subsystems,
types, rules, work, figures), each read from a substrate source at render
time and each fingerprinted (except the crew table, which is live state).
The classes from DerivedSectionsArePresent down pin, per section: it lands
with its derived-caption when its source exists, it is ABSENT when its source
is not, a --box render carries no crew and no path, and every new fingerprint
label is the ONLY label that sees an edit to its own source.
"""
from __future__ import annotations

import html
import importlib.util as _ilu
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "vault" / "tools" / "tropo-render-studio-map.py"
OUTPUT_REL = Path("boards") / "po" / "studio-map.html"
RESOURCES_REL = Path("vault") / "templates" / "root-docs" / "studio-map-resources.md"


def _load(name: str, path: Path):
    spec = _ilu.spec_from_file_location(name, path)
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_map = _load("v195_render_studio_map", TOOL)

#: Every link the ONE declared resources file promises. Read from the file
#: itself rather than restated here: a list restated in the test is a list that
#: drifts, and the point of the declared file is that it is the only place.
DECLARED_LINKS = re.findall(
    r"^- \[[^\]]+\]\(([^)]+)\)",
    (ROOT / RESOURCES_REL).read_text(encoding="utf-8"),
    re.MULTILINE,
)


def run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=180,
    )


#: Wave 2 (f0151b4347af) — the sources the DERIVED sections read. Copied from
#: this studio into a fixture by make_studio(..., with_derived=True), so a test
#: can delete or edit any one of them without touching a governed original.
INDEX_REL = Path("vault") / "00-index.jsonl"
CONTROL_REL = Path(".tropo") / "TROPO-CONTROL.md"
DIGEST_REL = Path(".tropo") / "boot-digest.md"
VERSION_REL = Path(".tropo") / "version.md"
REGISTRY_REL = Path(".tropo-studio") / "registries" / "subsystem-registry.jsonl"
CREW_BRIEF_REL = Path("00-crew-brief.md")
REVIEW_REL = Path("docs") / "architecture-review-v4" / "tropo-l1-architecture-review.md"
REVIEW_SVG_REL = Path("docs") / "architecture-review-v4" / "svg"
DERIVED_FILES = (CONTROL_REL, DIGEST_REL, VERSION_REL, REGISTRY_REL, CREW_BRIEF_REL, REVIEW_REL)

#: The five derived sections, by the `map-<name>` class each carries.
DERIVED_SECTIONS = ("subsystems", "types", "rules", "work", "figures")

#: The counts line every subsystem box gains (middle dot U+00B7).
COUNTS_RE = re.compile(r"\d+ tools · \d+ capsules · \d+ playbooks · \d+ skills")

#: The fingerprint labels the derived sections add, as PREFIXES: the capsules
#: label carries a `[N]` count suffix the way the subsystems label already does.
LABEL_HUB_COUNTS = f"hub-counts@{INDEX_REL.as_posix()}"
LABEL_CAPSULES = f"capsules@{INDEX_REL.as_posix()}["
LABEL_REGISTRY = REGISTRY_REL.as_posix()
LABEL_CONTROL = CONTROL_REL.as_posix()
LABEL_DIGEST = DIGEST_REL.as_posix()
LABEL_VERSION = VERSION_REL.as_posix()
LABEL_FIGURES = f"review-figures@{REVIEW_REL.as_posix()}"
DERIVED_LABELS = (
    LABEL_HUB_COUNTS,
    LABEL_CAPSULES,
    LABEL_REGISTRY,
    LABEL_CONTROL,
    LABEL_DIGEST,
    LABEL_VERSION,
    LABEL_FIGURES,
)


def make_studio(
    tmp: Path,
    with_resources: bool = True,
    with_agents: bool = True,
    with_derived: bool = False,
) -> Path:
    """A temp studio carrying the real inputs: the Map, the index (so the nine
    hubs are the real nine), and the resources file. `with_derived` adds the
    sources the derived sections read (kernel control, boot digest, version,
    subsystem registry, crew brief, the architecture review and its SVGs)."""
    studio = tmp / "studio"
    (studio / "docs").mkdir(parents=True)
    (studio / "vault").mkdir(parents=True)
    shutil.copy2(ROOT / "docs" / "tropo-studio-map.md", studio / "docs" / "tropo-studio-map.md")
    shutil.copy2(ROOT / "vault" / "00-index.jsonl", studio / "vault" / "00-index.jsonl")
    if with_resources:
        (studio / RESOURCES_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / RESOURCES_REL, studio / RESOURCES_REL)
    if with_agents:
        for slug in ("po", "metis"):
            home = studio / "agents" / slug
            home.mkdir(parents=True)
            (home / f"{slug}-activation.md").write_text(
                f'---\ncharter_uid: "0000{slug[:4]}"\n---\n\n# {slug}\n',
                encoding="utf-8",
            )
    if with_derived:
        for rel in DERIVED_FILES:
            (studio / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, studio / rel)
        shutil.copytree(ROOT / REVIEW_SVG_REL, studio / REVIEW_SVG_REL)
    return studio


# --- Wave 2 helpers: read the fixture's sources INDEPENDENTLY of the tool, so
# --- an expectation never comes from the code under test.


def render_of(studio: Path, *args: str) -> str:
    """Render the studio (exit 0 or raise with stderr) and return the html."""
    result = run_tool("--vault-path", str(studio), *args)
    if result.returncode != 0:
        raise AssertionError(f"render failed ({result.returncode}): {result.stderr}")
    return (studio / OUTPUT_REL).read_text(encoding="utf-8")


def section_of(html_text: str, name: str) -> "str | None":
    """The inner html of `<section class="map-derived map-<name>">`, or None."""
    m = re.search(
        rf'<section class="map-derived map-{name}"[^>]*>(.*?)</section>',
        html_text,
        re.DOTALL,
    )
    return m.group(1) if m else None


def has_section_class(html_text: str, name: str) -> bool:
    """Whether any element carries the `map-<name>` class. A class ATTRIBUTE,
    not a bare substring: a stylesheet rule for `.map-<name>` in the head is
    not a rendered section."""
    return re.search(rf'class="[^"]*\bmap-{name}\b[^"]*"', html_text) is not None


def derived_caption(section: str) -> "str | None":
    """Plain text of the section's `<p class="derived-caption">`, or None."""
    m = re.search(r'<p class="derived-caption">(.*?)</p>', section, re.DOTALL)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else None


def index_lines(studio: Path) -> "list[str]":
    return [
        line
        for line in (studio / INDEX_REL).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row(line: str) -> "dict | None":
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def filter_index(studio: Path, keep) -> int:
    """Rewrite the fixture index with only the rows `keep` accepts; returns the
    number dropped. Lines are carried byte-identical, never re-serialized."""
    kept, dropped = [], 0
    for line in index_lines(studio):
        row = _row(line)
        if row is not None and not keep(row):
            dropped += 1
            continue
        kept.append(line)
    (studio / INDEX_REL).write_text("\n".join(kept) + "\n", encoding="utf-8")
    return dropped


def edit_index_row(studio: Path, match, mutate) -> dict:
    """Re-serialize ONE line of the fixture index — the first row `match`
    accepts, after `mutate` — leaving every other line byte-identical, so an
    edit meant for one derived input cannot leak into another by accident."""
    lines = index_lines(studio)
    for i, line in enumerate(lines):
        row = _row(line)
        if row is not None and match(row):
            mutate(row)
            lines[i] = json.dumps(row, ensure_ascii=False)
            (studio / INDEX_REL).write_text("\n".join(lines) + "\n", encoding="utf-8")
            return row
    raise AssertionError("no index row matched the edit")


#: The per-hub census the subsystems table and the boxes carry, in the
#: contract's column order.
COUNT_TYPES = (
    "tool",
    "capsule-definition",
    "playbook",
    "how-to",
    "session-agent",
    "action",
    "loop",
    "pipeline",
)


def hub_census(studio: Path, hub_uid: str) -> "list[str]":
    """How many index rows of each COUNT_TYPES type tag `hub_uid` as a
    subsystem_hub — computed here, from the fixture, never from the tool."""
    counts = {t: 0 for t in COUNT_TYPES}
    for row in (_row(line) for line in index_lines(studio)):
        if row is None or row.get("type") not in counts:
            continue
        if hub_uid in (row.get("subsystem_hub") or []):
            counts[row["type"]] += 1
    return [str(counts[t]) for t in COUNT_TYPES]


def cell_texts(row_html: str) -> "list[str]":
    """The plain text of every <td> in one table row."""
    return [
        html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
    ]


def capsule_titles(studio: Path) -> "list[str]":
    return [
        str(row.get("title") or row.get("uid"))
        for row in (_row(line) for line in index_lines(studio))
        if row is not None and row.get("type") == "capsule-definition"
    ]


def hubs_with_capsules(studio: Path) -> "set[str]":
    hub_uids = {s["uid"] for s in render_map.read_subsystems(studio)}
    found: "set[str]" = set()
    for row in (_row(line) for line in index_lines(studio)):
        if row is not None and row.get("type") == "capsule-definition":
            found.update(h for h in (row.get("subsystem_hub") or []) if h in hub_uids)
    return found


def capsules_without_a_hub(studio: Path) -> int:
    return sum(
        1
        for row in (_row(line) for line in index_lines(studio))
        if row is not None
        and row.get("type") == "capsule-definition"
        and not row.get("subsystem_hub")
    )


def registry_last_releases(studio: Path) -> "dict[str, str]":
    """Highest release_version per subsystem_uid, version-tuple compared."""
    best: "dict[str, tuple[tuple[int, ...], str]]" = {}
    for line in (studio / REGISTRY_REL).read_text(encoding="utf-8").splitlines():
        row = _row(line) if line.strip() else None
        if row is None:
            continue
        uid, version = row.get("subsystem_uid"), row.get("release_version")
        if not uid or not version:
            continue
        key = tuple(int(p) for p in re.findall(r"\d+", str(version)))
        if uid not in best or key > best[uid][0]:
            best[uid] = (key, str(version))
    return {uid: version for uid, (_key, version) in best.items()}


def invariant_titles(studio: Path) -> "list[str]":
    """Titles of the numbered items under '## 3. OS-Level Invariants', with the
    period the bold carries stripped so the check is the same whether the
    renderer keeps it or not."""
    text = (studio / CONTROL_REL).read_text(encoding="utf-8")
    section = text.split("\n## 3. OS-Level Invariants", 1)[1].split("\n## ", 1)[0]
    return [t.rstrip(".") for t in re.findall(r"^\d+\. \*\*(.+?)\*\*", section, re.MULTILINE)]


def op_titles(studio: Path) -> "list[str]":
    text = (studio / DIGEST_REL).read_text(encoding="utf-8")
    section = text.split("\n## The 15 Operating Principles", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\d+\. \*\*(.+?)\*\*", section, re.MULTILINE)


def version_text(studio: Path) -> str:
    for line in (studio / VERSION_REL).read_text(encoding="utf-8").splitlines():
        if line.strip():
            return line.strip()
    raise AssertionError("fixture version.md is empty")


def crew_first_table(studio: Path) -> "tuple[list[str], list[list[str]]]":
    """Header cells and rows of the FIRST pipe table between the crew-table
    markers of the fixture's crew brief."""
    text = (studio / CREW_BRIEF_REL).read_text(encoding="utf-8")
    block = text.split("<!-- crew-table:start -->", 1)[1].split("<!-- crew-table:end -->", 1)[0]
    table: "list[str]" = []
    for line in block.splitlines():
        if line.strip().startswith("|"):
            table.append(line.strip())
        elif table:
            break
    cells = lambda line: [c.strip() for c in line.strip("|").split("|")]  # noqa: E731
    return cells(table[0]), [cells(line) for line in table[2:]]


def review_caption(studio: Path, svg_name: str) -> str:
    """The View cell Appendix A gives `svg/<svg_name>`."""
    text = (studio / REVIEW_REL).read_text(encoding="utf-8")
    m = re.search(
        rf"^\| `svg/{re.escape(svg_name)}` \| (.+?) \|[ \t]*$", text, re.MULTILINE
    )
    if not m:
        raise AssertionError(f"Appendix A has no row for svg/{svg_name}")
    return m.group(1).strip()


def derived_inputs(studio: Path) -> "list[tuple[str, str]]":
    """fingerprint_inputs(...) with the root passed, as the render calls it."""
    return render_map.fingerprint_inputs(
        studio / render_map.SOURCE_REL,
        studio / RESOURCES_REL,
        render_map.read_subsystems(studio),
        root=studio,
    )


class TheVisualAndTheResources(unittest.TestCase):
    """(a) — rendered on this studio: the generated visual and the declared
    resources both land, and the visual names every hub the index declares."""

    @classmethod
    def setUpClass(cls) -> None:
        result = run_tool("--vault-path", str(ROOT))
        assert result.returncode == 0, result.stderr
        cls.html = (ROOT / OUTPUT_REL).read_text(encoding="utf-8")
        cls.subsystems = render_map.read_subsystems(ROOT)

    def test_the_visual_is_inline_svg_with_a_labeled_box_per_subsystem(self) -> None:
        self.assertEqual(
            len(self.subsystems),
            9,
            "AC8 names nine subsystem hubs; the index now declares a different "
            "number, so either the substrate moved or the reader is wrong",
        )
        self.assertIn("<svg class=\"studio-viz\"", self.html)
        boxes = self.html.count('class="viz-box"')
        self.assertEqual(
            boxes,
            len(self.subsystems),
            "one box per subsystem, generated -- not a hand-drawn picture that "
            "keeps its old shape after a tenth hub arrives",
        )
        for sub in self.subsystems:
            self.assertIn(
                sub["title"][:25],
                self.html,
                f"{sub['uid']} has no label in the visual",
            )
            self.assertIn(
                f"{sub['uid']}.md",
                self.html,
                f"{sub['uid']}'s box links nowhere",
            )

    def test_the_three_bands_are_the_location_contract_s_layers(self) -> None:
        for label in ("Kernel", "Primitives", "Apps"):
            self.assertIn(f">{label}<", self.html)
        for folder in (".tropo/", "vault/", "agents/"):
            self.assertIn(folder, self.html)

    def test_the_resources_section_carries_every_declared_link(self) -> None:
        self.assertIn("<h2>Resources</h2>", self.html)
        self.assertTrue(DECLARED_LINKS, "the declared resources file has no links")
        for href in DECLARED_LINKS:
            if href.startswith("http"):
                needle = href
            else:  # rewritten from Studio-root-relative to boards/po/-relative
                needle = Path(href).name
            self.assertIn(
                needle,
                self.html,
                f"declared resource {href} did not reach the render",
            )


class BoxRender(unittest.TestCase):
    """(b) — a box carries no path from the machine that built it, and no
    overlay: it has no customer studio yet."""

    def test_box_output_has_no_absolute_path_and_no_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            self.assertEqual(
                run_tool("--vault-path", str(studio), "--box", "--overlay").returncode,
                0,
            )
            html = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            self.assertNotIn("/Users/", html)
            self.assertNotIn(str(studio), html)
            self.assertNotIn("This studio</h2>", html)
            self.assertIn("<h2>Resources</h2>", html, "a box still ships the resources")
            self.assertIn('class="viz-box"', html, "a box still ships the visual")

    def test_a_box_render_links_only_what_the_box_carries(self) -> None:
        """AC8 'every link resolves' (Vela's read of the sealed candidate #2,
        f0152975b448: nine of 114 links dead in the box). A --box render turns a
        link whose target the box lacks into text; a link whose target ships keeps
        its anchor; the studio's own render (no --box) keeps every anchor."""
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            src = studio / "docs" / "tropo-studio-map.md"
            src.write_text(
                src.read_text(encoding="utf-8")
                + "\n\nSee [Gone](../vault/files/zzzzzzzz-not-in-this-box.md) and [Here](tropo-studio-map.md).\n",
                encoding="utf-8",
            )
            self.assertEqual(run_tool("--vault-path", str(studio), "--box").returncode, 0)
            html = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            self.assertIn('<span class="unshipped" title="not in this box">Gone</span>', html)
            self.assertNotIn("zzzzzzzz-not-in-this-box", html)
            self.assertRegex(html, r'<a href="[^"]*tropo-studio-map\.md">Here</a>')
            # negative control: the studio's own render links what it names
            self.assertEqual(run_tool("--vault-path", str(studio)).returncode, 0)
            html = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            self.assertRegex(html, r'<a href="[^"]*zzzzzzzz-not-in-this-box\.md">Gone</a>')

    def test_a_box_without_an_identity_manifest_reads_neutrally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))  # no .tropo/studio-identity.md
            self.assertEqual(
                run_tool("--vault-path", str(studio), "--box").returncode, 0
            )
            html = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            self.assertIn("This is the Studio Map for this studio.", html)


class OverlayRender(unittest.TestCase):
    """(c) — --overlay names this studio's own agents."""

    def test_overlay_lists_the_agents_of_the_studio_it_points_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            self.assertEqual(
                run_tool("--vault-path", str(studio), "--overlay").returncode, 0
            )
            html = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            self.assertIn("This studio</h2>", html)
            self.assertIn("<h3>Agents</h3>", html)
            for slug in ("po", "metis"):
                self.assertIn(f"{slug}-activation.md", html)


class StalenessCoversEveryInput(unittest.TestCase):
    """(d) — the pair. The old fingerprint watched the Map alone; an edit to
    the resources file changed the render and nothing said so."""

    def test_check_stale_passes_fails_on_a_resources_edit_then_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            self.assertEqual(run_tool("--vault-path", str(studio)).returncode, 0)

            first = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("FRESH", first.stdout)

            resources = studio / RESOURCES_REL
            resources.write_text(
                resources.read_text(encoding="utf-8")
                + "- [A late arrival](CHANGELOG.md) — added after the render.\n",
                encoding="utf-8",
            )
            second = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(
                second.returncode,
                1,
                "an edit to the resources file must make the render stale",
            )
            self.assertIn("STALE", second.stderr)

            self.assertEqual(run_tool("--vault-path", str(studio)).returncode, 0)
            third = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertIn("FRESH", third.stdout)
            self.assertIn("A late arrival", (studio / OUTPUT_REL).read_text(encoding="utf-8"))

    def test_a_subsystem_rename_in_the_index_also_makes_it_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            self.assertEqual(run_tool("--vault-path", str(studio)).returncode, 0)
            index = studio / "vault" / "00-index.jsonl"
            before = render_map.read_subsystems(studio)
            index.write_text(
                index.read_text(encoding="utf-8").replace(
                    "Tropo Rendering", "Tropo Renderings"
                ),
                encoding="utf-8",
            )
            self.assertNotEqual(
                render_map.subsystems_fingerprint(before),
                render_map.subsystems_fingerprint(render_map.read_subsystems(studio)),
                "the rename did not reach the subsystem list the render reads",
            )
            self.assertEqual(
                run_tool("--vault-path", str(studio), "--check-stale").returncode, 1
            )

    def test_the_map_s_own_body_fingerprint_is_still_published(self) -> None:
        """tropo-validate.py Check 37 reads this exact comment. Extending the
        fingerprint must not take the validator's instrument away."""
        html = (ROOT / OUTPUT_REL).read_text(encoding="utf-8")
        self.assertIn("<!-- tropo:derived-render", html)
        self.assertRegex(html, r"tropo:source-body-sha256:[0-9a-f]{64}")
        self.assertRegex(html, r"tropo:render-fingerprint:[0-9a-f]{64}")
        self.assertIn("tropo:render-inputs:", html)
        self.assertIn(RESOURCES_REL.as_posix(), html)


class MissingResourcesIsLoud(unittest.TestCase):
    """(e) — the declared file is required. Mike asked for links on the shipped
    HTML; a render that drops them without a word is the defect."""

    def test_render_refuses_and_names_the_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_resources=False)
            result = run_tool("--vault-path", str(studio))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("studio-map-resources.md", result.stderr)
            self.assertFalse(
                (studio / OUTPUT_REL).exists(),
                "a refused render must leave no half-built artifact behind",
            )


# ---------------------------------------------------------------------------
# Wave 2 (f0151b4347af): the derived sections.
# ---------------------------------------------------------------------------


class DerivedSectionsArePresent(unittest.TestCase):
    """Rendered once on a fixture that carries every source: each derived
    section lands, says it is derived, and shows one fact only its source
    could have supplied. The defect class: a section that is hand-written
    in the generator (and so cannot move when the substrate does), or one
    that renders as an empty heading because the reader silently found
    nothing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.studio = make_studio(Path(cls._tmp.name), with_derived=True)
        cls.html = render_of(cls.studio)
        cls.subsystems = render_map.read_subsystems(cls.studio)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _section(self, name: str) -> str:
        section = section_of(self.html, name)
        self.assertIsNotNone(section, f"no <section class=\"map-derived map-{name}\"> in the render")
        return section  # type: ignore[return-value]

    def test_every_derived_section_says_it_is_derived_at_render(self) -> None:
        """Catches a derived section shipped without its provenance line — a
        reader must be told the block is read from the substrate at render,
        not hand-maintained in the Map."""
        for name in DERIVED_SECTIONS:
            with self.subTest(section=name):
                caption = derived_caption(self._section(name))
                self.assertIsNotNone(caption, f"map-{name} has no <p class=\"derived-caption\">")
                self.assertIn("derived from", caption.lower(), f"map-{name}: {caption!r}")
                self.assertIn("at render", caption.lower(), f"map-{name}: {caption!r}")

    def test_map_subsystems_lists_the_nine_hubs_with_their_counts(self) -> None:
        """Catches a subsystems section that is not read from the index: every
        one of the nine hubs the index declares must have a row, and that
        row's counts must be the per-hub census (COUNT_TYPES, in order) of
        the rows tagging it — recomputed here from the fixture, so a count
        the tool hard-codes, mislabels, or keys on the wrong tag fails."""
        self.assertEqual(len(self.subsystems), 9)
        section = self._section("subsystems")
        for sub in self.subsystems:
            row = re.search(
                rf"<tr[^>]*>(?:(?!</tr>).)*{re.escape(sub['uid'])}\.md.*?</tr>",
                section,
                re.DOTALL,
            )
            self.assertIsNotNone(row, f"hub {sub['uid']} ({sub['title']}) has no row")
            cells = cell_texts(row.group(0))
            expected = hub_census(self.studio, sub["uid"])
            width = len(expected)
            windows = [cells[i : i + width] for i in range(len(cells) - width + 1)]
            self.assertIn(
                expected,
                windows,
                f"{sub['title']}: census {expected} is not a run of that row's cells {cells}",
            )

    def test_map_subsystems_shows_the_registry_s_last_release_per_hub(self) -> None:
        """Catches a subsystems section that never reads the subsystem
        registry: the highest release_version the registry records for a hub
        must reach the render."""
        last = registry_last_releases(self.studio)
        self.assertTrue(last, "the fixture registry records no releases")
        section = html.unescape(self._section("subsystems"))
        for uid, version in sorted(last.items()):
            self.assertIn(version, section, f"hub {uid}'s last release {version} is not in map-subsystems")

    def test_the_visual_s_boxes_carry_a_counts_line_each(self) -> None:
        """Catches the visual keeping its pre-Wave-2 shape: each of the nine
        boxes gains one `N tools · N capsules · N playbooks · N skills` line."""
        svg = re.search(r'<svg class="studio-viz".*?</svg>', self.html, re.DOTALL)
        self.assertIsNotNone(svg, "no generated visual in the render")
        lines = COUNTS_RE.findall(html.unescape(svg.group(0)))
        self.assertEqual(
            len(lines),
            len(self.subsystems),
            f"expected one counts line per box, found {len(lines)}: {lines}",
        )

    def test_map_types_groups_capsules_per_hub_in_details_blocks(self) -> None:
        """Catches a types section that is not the index's capsule-definition
        rows: a <details> per hub that has capsules, the capsule titles from
        the index, and an unassigned group for the rows that name no hub."""
        section = self._section("types")
        self.assertGreaterEqual(
            section.count("<details"),
            len(hubs_with_capsules(self.studio)),
            "fewer <details> blocks than hubs that have capsules",
        )
        titles = capsule_titles(self.studio)
        self.assertTrue(titles, "the fixture index has no capsule-definition rows")
        unescaped = html.unescape(section)
        for title in titles:
            if len(title) <= 40:  # long titles may be shortened for display
                self.assertIn(title, unescaped, f"capsule {title!r} is not in map-types")
        if capsules_without_a_hub(self.studio):
            self.assertIn("unassigned", unescaped.lower(), "capsules without a hub have no group")

    def test_map_rules_lists_the_invariants_and_op_titles_with_links_home(self) -> None:
        """Catches a rules section that restates the invariants rather than
        reading TROPO-CONTROL.md: every numbered invariant title, in an <ol>,
        each linking home by a relative href; and the fifteen OP titles."""
        section = self._section("rules")
        unescaped = html.unescape(section)
        invariants = invariant_titles(self.studio)
        self.assertIn("UID requirement", invariants)
        for title in invariants:
            self.assertIn(title, unescaped, f"invariant {title!r} is not in map-rules")
        ordered = re.search(r"<ol[^>]*>(.*?)</ol>", section, re.DOTALL)
        self.assertIsNotNone(ordered, "the invariants are an <ol>")
        items = re.findall(r"<li[^>]*>(.*?)</li>", ordered.group(1), re.DOTALL)
        self.assertEqual(len(items), len(invariants), "one <li> per invariant")
        home = f'href="../../{CONTROL_REL.as_posix()}'
        for number, item in enumerate(items, 1):
            self.assertIn(
                home, item, f"invariant {number} does not link to TROPO-CONTROL.md relative to boards/po/"
            )
        principles = op_titles(self.studio)
        self.assertEqual(len(principles), 15)
        for title in principles:
            self.assertIn(title, unescaped, f"operating principle {title!r} is not in map-rules")

    def test_map_work_carries_the_version_and_the_crew_table(self) -> None:
        """Catches a work section that hand-writes the release: the line must
        carry version.md's text, and (studio mode) the crew brief's first
        table with its agents."""
        section = self._section("work")
        unescaped = html.unescape(section)
        self.assertIn(version_text(self.studio), unescaped)
        header, rows = crew_first_table(self.studio)
        self.assertTrue(rows, "the fixture crew brief's first table has no rows")
        self.assertIn("<table", section, "studio mode renders the crew table")
        for cell in header:
            self.assertIn(cell, unescaped, f"crew table header {cell!r} missing")
        for row in rows:
            self.assertIn(row[0], unescaped, f"crew member {row[0]!r} missing from map-work")

    def test_map_figures_embeds_the_four_review_diagrams_with_their_captions(self) -> None:
        """Catches figures that point at docs/ from the wrong directory (a
        broken <img> in boards/po/) or that lose Appendix A's caption."""
        section = self._section("figures")
        images = re.findall(r"<img[^>]+>", section)
        self.assertEqual(len(images), 4, f"expected the four selected figures, got {images}")
        wanted = f"../../{REVIEW_SVG_REL.as_posix()}/01-system-map.svg"
        self.assertTrue(
            any(f'="{wanted}"' in img for img in images),
            f"no <img> points at {wanted}; images: {images}",
        )
        for name in ("02-capsule-type-system", "07-pipelines-and-loops", "10-write-path"):
            self.assertIn(f"../../{REVIEW_SVG_REL.as_posix()}/{name}.svg", section)
        self.assertIn("<figcaption", section)
        self.assertIn(review_caption(self.studio, "01-system-map.svg"), html.unescape(section))


class DerivedSectionsAreAbsentWithoutTheirSource(unittest.TestCase):
    """Each section is ABSENT — no class, no empty heading — when its source
    is not there, and the render still exits 0. The defect: a box whose Map
    shows 'Rules' over nothing because the box has no boot digest, or a
    render that dies on a pre-genesis studio with no version file."""

    def _assert_absent(self, studio: Path, name: str, *args: str) -> str:
        html_text = render_of(studio, *args)
        self.assertFalse(
            has_section_class(html_text, name),
            f"map-{name} rendered although its source is absent",
        )
        return html_text

    def test_no_subsystem_hubs_in_the_index_means_no_map_subsystems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            root = render_map.SUBSYSTEMS_ROOT_UID
            dropped = filter_index(
                studio,
                lambda r: not (
                    r.get("type") == "project" and root in (r.get("member_of") or [])
                ),
            )
            self.assertEqual(dropped, 9, "the nine hub projects, and only those")
            self.assertEqual(render_map.read_subsystems(studio), [])
            self._assert_absent(studio, "subsystems")

    def test_no_capsule_rows_in_the_index_means_no_map_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            self.assertGreater(
                filter_index(studio, lambda r: r.get("type") != "capsule-definition"), 0
            )
            html_text = self._assert_absent(studio, "types")
            self.assertTrue(has_section_class(html_text, "rules"), "only map-types should go")

    def test_no_control_file_and_no_boot_digest_means_no_map_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            (studio / CONTROL_REL).unlink()
            (studio / DIGEST_REL).unlink()
            html_text = self._assert_absent(studio, "rules")
            self.assertTrue(has_section_class(html_text, "work"), "only map-rules should go")

    def test_no_version_and_no_crew_brief_means_no_map_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            (studio / VERSION_REL).unlink()
            (studio / CREW_BRIEF_REL).unlink()
            html_text = self._assert_absent(studio, "work")
            self.assertTrue(has_section_class(html_text, "rules"), "only map-work should go")

    def test_no_version_in_box_mode_means_no_map_work_even_with_a_crew_brief(self) -> None:
        """A box never renders the crew table, so with no version file there
        is nothing left for map-work to say."""
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            (studio / VERSION_REL).unlink()
            self.assertTrue((studio / CREW_BRIEF_REL).is_file())
            self._assert_absent(studio, "work", "--box")

    def test_no_architecture_review_means_no_map_figures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            (studio / REVIEW_REL).unlink()
            self.assertTrue((studio / REVIEW_SVG_REL).is_dir(), "the SVGs alone are not a source")
            html_text = self._assert_absent(studio, "figures")
            self.assertTrue(has_section_class(html_text, "work"), "only map-figures should go")


class BoxHonestyWithDerivedSources(unittest.TestCase):
    """--box with every derived source present: the version ships, the crew
    does not, and no path from the building machine or its studio leaks.
    The defect: a customer's first Map naming the vendor's agents, or the
    vendor's disk."""

    def test_a_box_carries_the_version_but_no_crew_table_and_no_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            html_text = render_of(studio, "--box")
            self.assertNotIn("/Users/", html_text)
            self.assertNotIn("argo-os", html_text)
            self.assertNotIn(str(studio), html_text)
            self.assertNotIn("<h3>Crew", html_text)
            _header, rows = crew_first_table(studio)
            slugs = [row[0] for row in rows]
            self.assertTrue(slugs)
            for slug in slugs:
                self.assertNotIn(f"<td>{slug}</td>", html_text, f"crew cell for {slug} in a box")
            work = section_of(html_text, "work")
            self.assertIsNotNone(work, "a box still carries map-work: the version is box content")
            self.assertIn(version_text(studio), html.unescape(work))
            self.assertNotIn("<table", work, "a box's map-work must not carry the crew table")
            for slug in slugs:
                self.assertNotIn(slug, html.unescape(work), f"{slug} named in a box's map-work")


class DerivedFingerprintLabels(unittest.TestCase):
    """The composite lists one label per derived source when it exists, and
    drops it when the source is gone — the crew brief being the one input
    deliberately left out. The defect: a label that is always there (so a
    missing source hashes as something and the render never goes stale when
    it arrives) or one that is never there (an unfingerprinted input)."""

    def test_every_derived_label_is_listed_when_its_source_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            inputs = derived_inputs(studio)
            labels = [label for label, _digest in inputs]
            for prefix in DERIVED_LABELS:
                matches = [label for label in labels if label.startswith(prefix)]
                self.assertEqual(len(matches), 1, f"{prefix}: expected one label, found {matches} in {labels}")
            for label, digest in inputs:
                self.assertRegex(digest, r"^[0-9a-f]{64}$", f"{label}: not a sha256")
            # The three Wave-1 labels are still first in line.
            self.assertEqual(labels[0], render_map.SOURCE_REL.as_posix())
            self.assertEqual(labels[1], RESOURCES_REL.as_posix())
            self.assertTrue(labels[2].startswith(f"subsystems@{INDEX_REL.as_posix()}["), labels)
            self.assertFalse(
                [label for label in labels if "crew-brief" in label],
                "the crew brief is live state and must not be fingerprinted",
            )
            capsules = [label for label in labels if label.startswith(LABEL_CAPSULES)][0]
            self.assertEqual(
                capsules, f"{LABEL_CAPSULES}{len(capsule_titles(studio))}]",
                "the capsules label carries the capsule-row count",
            )

    def test_a_label_is_omitted_when_its_source_is_removed(self) -> None:
        removals = (
            (INDEX_REL, {LABEL_HUB_COUNTS, LABEL_CAPSULES}),
            (REGISTRY_REL, {LABEL_REGISTRY}),
            (CONTROL_REL, {LABEL_CONTROL}),
            (DIGEST_REL, {LABEL_DIGEST}),
            (VERSION_REL, {LABEL_VERSION}),
            (REVIEW_REL, {LABEL_FIGURES}),
        )
        for rel, gone in removals:
            with self.subTest(removed=rel.as_posix()), tempfile.TemporaryDirectory() as tmp_str:
                studio = make_studio(Path(tmp_str), with_derived=True)
                (studio / rel).unlink()
                labels = [label for label, _digest in derived_inputs(studio)]
                for prefix in DERIVED_LABELS:
                    present = any(label.startswith(prefix) for label in labels)
                    if prefix in gone:
                        self.assertFalse(present, f"{prefix} listed although {rel.as_posix()} is gone: {labels}")
                    else:
                        self.assertTrue(present, f"{prefix} dropped although only {rel.as_posix()} is gone: {labels}")

    def test_the_crew_brief_is_live_state_and_never_makes_the_render_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            render_of(studio)
            brief = studio / CREW_BRIEF_REL
            brief.write_text(brief.read_text(encoding="utf-8") + "x", encoding="utf-8")
            result = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FRESH", result.stdout)


def _append_a_character(rel: Path):
    """A byte body_sha256 cannot normalize away (a trailing newline would be)."""

    def edit(studio: Path) -> None:
        path = studio / rel
        path.write_text(path.read_text(encoding="utf-8") + "x", encoding="utf-8")

    return edit


def _move_one_tool_to_another_hub(studio: Path) -> None:
    hub_uids = [s["uid"] for s in render_map.read_subsystems(studio)]

    def mutate(row: dict) -> None:
        current = row["subsystem_hub"]
        row["subsystem_hub"] = [next(uid for uid in hub_uids if uid not in current)]

    edit_index_row(
        studio,
        lambda r: r.get("type") == "tool" and bool(r.get("subsystem_hub")),
        mutate,
    )


def _rename_one_capsule(studio: Path) -> None:
    edit_index_row(
        studio,
        lambda r: r.get("type") == "capsule-definition",
        lambda r: r.__setitem__("title", f"{r.get('title', '')} (renamed)"),
    )


def _edit_one_figure_caption(studio: Path) -> None:
    path = studio / REVIEW_REL
    text, count = re.subn(
        r"^(\| `svg/01-system-map\.svg` \| .+?)( \|[ \t]*)$",
        r"\1 (caption edited)\2",
        path.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise AssertionError("Appendix A row for 01-system-map.svg not found")
    path.write_text(text, encoding="utf-8")


class EachDerivedLabelSeesOnlyItsOwnEdit(unittest.TestCase):
    """Per new label: a render is FRESH, an edit to that label's source makes
    --check-stale exit 1 (positive), and — the mutation — with that one label
    filtered out of the inputs the composite is UNCHANGED across the edit, so
    the label is the only thing that saw it. The defect on the positive side
    is an input the composite cannot see; on the mutation side, a label that
    passes the positive only because a sibling (say, a whole-file hash of the
    index) happens to move too, which would leave the label itself dead."""

    def _assert_label_sees_only_its_edit(self, prefix: str, edit) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str), with_derived=True)
            render_of(studio)
            fresh = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(fresh.returncode, 0, f"{prefix}: {fresh.stderr}")
            self.assertIn("FRESH", fresh.stdout, prefix)

            before = derived_inputs(studio)
            edit(studio)
            after = derived_inputs(studio)

            stale = run_tool("--vault-path", str(studio), "--check-stale")
            self.assertEqual(
                stale.returncode, 1, f"{prefix}: an edit to this input must make the render stale"
            )
            self.assertIn("STALE", stale.stderr, prefix)

            digest_before = [d for label, d in before if label.startswith(prefix)]
            digest_after = [d for label, d in after if label.startswith(prefix)]
            self.assertEqual(len(digest_before), 1, f"{prefix}: not listed exactly once before the edit: {before}")
            self.assertEqual(len(digest_after), 1, f"{prefix}: not listed exactly once after the edit: {after}")
            self.assertNotEqual(
                digest_before[0], digest_after[0], f"{prefix}: this label did not see its own edit"
            )
            without = lambda inputs: [e for e in inputs if not e[0].startswith(prefix)]  # noqa: E731
            self.assertEqual(
                render_map.composite_fingerprint(without(before)),
                render_map.composite_fingerprint(without(after)),
                f"{prefix}: with this label filtered out the composite still moved, so another "
                f"input saw the edit too and this label is not what carries it",
            )

    def test_hub_counts_label_sees_a_tool_changing_hub(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_HUB_COUNTS, _move_one_tool_to_another_hub)

    def test_capsules_label_sees_a_capsule_rename(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_CAPSULES, _rename_one_capsule)

    def test_registry_label_sees_a_registry_edit(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_REGISTRY, _append_a_character(REGISTRY_REL))

    def test_control_label_sees_a_tropo_control_edit(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_CONTROL, _append_a_character(CONTROL_REL))

    def test_digest_label_sees_a_boot_digest_edit(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_DIGEST, _append_a_character(DIGEST_REL))

    def test_version_label_sees_a_version_edit(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_VERSION, _append_a_character(VERSION_REL))

    def test_review_figures_label_sees_a_caption_edit(self) -> None:
        self._assert_label_sees_only_its_edit(LABEL_FIGURES, _edit_one_figure_caption)


class TheFileWinsOverAStaleRow(unittest.TestCase):
    """Metis G121, 2026-09-05, measured on her own clone: the hub file said
    `vault/` (the default) and the --only-written index row still said `boards/`;
    the first cut used the default as its absent-sentinel and took the row. The
    file is the source; the row is consulted only when the file has no key."""

    def test_file_home_equal_to_default_beats_a_stale_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            index = studio / "vault" / "00-index.jsonl"
            rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()]
            hub = next(r for r in rows if r.get("uid") == "99ed55fd")
            hub["subsystem_home"] = "boards/"  # the stale row
            index.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            hub_path = studio / str(hub.get("path") or "vault/files/99ed55fd.md")
            hub_path.parent.mkdir(parents=True, exist_ok=True)
            hub_path.write_text(
                "---\nuid: 99ed55fd\ntype: project\nsubsystem_home: vault/   # equals the default on purpose\n---\n\n# Tropo Agents\n",
                encoding="utf-8",
            )
            subs = {s["uid"]: s for s in render_map.read_subsystems(studio)}
            self.assertEqual(subs["99ed55fd"]["home"], "vault/", "the file's vault/ must win over the row's boards/")
            self.assertEqual(render_map.band_of(subs["99ed55fd"]["home"]), "primitives")

    def test_row_is_used_only_when_the_file_has_no_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            index = studio / "vault" / "00-index.jsonl"
            rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()]
            hub = next(r for r in rows if r.get("uid") == "99ed55fd")
            hub["subsystem_home"] = "agents/"
            index.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            hub_path = studio / str(hub.get("path") or "vault/files/99ed55fd.md")
            hub_path.parent.mkdir(parents=True, exist_ok=True)
            hub_path.write_text("---\nuid: 99ed55fd\ntype: project\n---\n\n# Tropo Agents\n", encoding="utf-8")
            subs = {s["uid"]: s for s in render_map.read_subsystems(studio)}
            self.assertEqual(subs["99ed55fd"]["home"], "agents/", "no key in the file: the row is the fallback")


class TheHomeComesFromTheHubFile(unittest.TestCase):
    """Metis G121, 2026-09-05, measured: a full index rebuild does not project
    `subsystem_home`, so a renderer that reads the key from the index ROW ships
    a picture with every hub collapsed into the vault band. The governed truth
    is the hub file's frontmatter; the index only finds the hub."""

    def test_an_index_row_without_the_key_still_lands_in_its_band_by_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            studio = make_studio(Path(tmp_str))
            index = studio / "vault" / "00-index.jsonl"
            rows = [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()]
            hub = next(r for r in rows if r.get("uid") == "99ed55fd")
            # The fixture index is built from the LIVE index, whose rows carry the
            # key on a clone that registered the hubs with --only and lack it on a
            # clone that ran a full rebuild (Metis G121 measured both, 2026-09-05).
            # A test must not depend on which machine runs it: strip the key here
            # so the fixture always models the full-rebuild shape this test is about.
            for r in rows:
                r.pop("subsystem_home", None)
                r.pop("home_folder", None)
            index.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            self.assertNotIn("subsystem_home", hub, "the fixture index must lack the key for this test to mean anything")
            hub_path = studio / str(hub.get("path") or "vault/files/99ed55fd.md")
            hub_path.parent.mkdir(parents=True, exist_ok=True)
            hub_path.write_text(
                "---\nuid: 99ed55fd\ntype: project\nsubsystem_home: agents/   # the folder this subsystem lives in\n---\n\n# Tropo Agents\n",
                encoding="utf-8",
            )
            subs = {s["uid"]: s for s in render_map.read_subsystems(studio)}
            self.assertEqual(subs["99ed55fd"]["home"], "agents/", "home must come from the hub file, not the row")
            self.assertEqual(render_map.band_of(subs["99ed55fd"]["home"]), "apps")
            self.assertEqual(run_tool("--vault-path", str(studio), "--box").returncode, 0)
            html_text = (studio / OUTPUT_REL).read_text(encoding="utf-8")
            box = re.search(r'<a href="[^"]*99ed55fd\.md"[^>]*>(.*?)</a>', html_text, re.DOTALL)
            self.assertIsNotNone(box, "the Agents hub has a box")
            self.assertIn(">agents/<", box.group(1), "the box shows the home read from the hub file")
            # and the fingerprint sees a re-homing: the same hub at a different home hashes differently
            moved = [dict(s, home="vault/") if s["uid"] == "99ed55fd" else s for s in subs.values()]
            self.assertNotEqual(
                render_map.subsystems_fingerprint(list(subs.values())),
                render_map.subsystems_fingerprint(moved),
                "a hub changing band must move the subsystems fingerprint",
            )


if __name__ == "__main__":
    unittest.main()
