#!/usr/bin/env python3
"""tropo-render-studio-map.py — B-7 (f01564310146): a DERIVED RENDER of the
canonical Studio Map, never a board. Takes boards/_shared/board.css for
STYLE ONLY — no fill-the-shape workflow, no judgment about what to surface;
the whole document renders, unconditionally, because a render is not a
board (see boards/_formats/README.md's "you do not build a rendering
engine" rule, which binds AGENT-authored boards, not this generator).

Output lives at boards/po/studio-map.html — Po is who shows it, the same
`boards/<agent>/` home every other rendered snapshot uses. Regenerate
whenever docs/tropo-studio-map.md moves; never hand-edit the output.

v1.95 Spine A AC8 (f015de6b3a18) — the Map ships as a HUMAN surface, so the
render grew three inputs and two modes beyond the Map itself:

  * an inline SVG of the subsystems and their homes, GENERATED from the nine
    subsystem hub projects that are members of `tropo-subsystems` in
    vault/00-index.jsonl — never hand-drawn, so a tenth hub draws itself;
  * a Resources section rendered from ONE declared file
    (vault/templates/root-docs/studio-map-resources.md) — add a resource
    there, never here; a missing file REFUSES rather than omitting silently;
  * `--overlay`, a live "This studio" section (agents, active projects,
    boards) read from the studio's own index at render time;
  * `--box`, which renders for a shipped box: no overlay (a box has no
    customer studio yet) and no absolute path from the building machine.

The staleness fingerprint covers EVERY input the render reads — the Map, the
resources file, and the subsystem list — so editing any one of them makes
--check-stale fail. The Map's own body-sha256 comment is kept verbatim
because tropo-validate.py's Check 37 reads it.

v1.95 A5 (task f0151b4347af, 2026-09-05) — the render grew five DERIVED
sections and a richer picture. Mike's commission, verbatim: "give orpheus a
high-burn set of instructions on how to clean up our documentation. I will
put her in a Fable 5.1 model and in ultracode mode. I want her to dispatch
subagents to do some work. I have 50 minutes where I can go high burn in
this session. I want to use our systems sources of truth. Start with the
l1-architecture-review.md (v4) as the guideposts. Then use that to fan out
and read capsules and other governance files to assemble a beautiful studio
map." Orpheus O38 extended this Metis-owned tool under that authorization.
The rule that binds every addition: nothing about the nine is written here;
every rich section is derived at render time from a source the render reads
and fingerprints —

  * the nine subsystems, with live counts per hub (index `subsystem_hub`
    tags) and the last release that touched each (the subsystem registry);
  * the governed types (every capsule-definition row of the index);
  * the rules that bind (TROPO-CONTROL.md's OS invariants and the boot
    digest's Operating Principle titles, parsed, never pasted);
  * where the work is (.tropo/version.md; the crew brief's operating table
    in studio mode only — live state, unfingerprinted, like the overlay);
  * the Review's own figures, by reference, captioned from its Appendix A.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import posixpath
import re
import sys
from pathlib import Path

SOURCE_REL = Path("docs") / "tropo-studio-map.md"
OUTPUT_REL = Path("boards") / "po" / "studio-map.html"
STYLESHEET_HREF = "../_shared/board.css"  # relative to boards/po/, per the kit's own convention

#: The ONE declared resources file (AC8). It lives under vault/ with a uid and
#: extraction_scope: ship, so the index-driven vault copier ships it at this
#: same path inside the box and the render finds it there unchanged.
RESOURCES_REL = Path("vault") / "templates" / "root-docs" / "studio-map-resources.md"
INDEX_REL = Path("vault") / "00-index.jsonl"

#: v1.95 A5 — the sources the derived sections read. Each is optional: an
#: absent source renders no section and no fingerprint entry (a box that has
#: no crew brief yet must not die for it), never a fabricated one.
REGISTRY_REL = Path(".tropo-studio") / "registries" / "subsystem-registry.jsonl"
CONTROL_REL = Path(".tropo") / "TROPO-CONTROL.md"
DIGEST_REL = Path(".tropo") / "boot-digest.md"
PRINCIPLES_REL = Path(".tropo-studio") / "operating-principles.md"
VERSION_REL = Path(".tropo") / "version.md"
REVIEW_REL = Path("docs") / "architecture-review-v4" / "tropo-l1-architecture-review.md"
REVIEW_HTML_REL = Path("docs") / "architecture-review-v4" / "tropo-l1-architecture-review.html"
CREW_BRIEF_REL = Path("00-crew-brief.md")

#: The index types counted per hub, in display order, and the words a human
#: reads for each. A type absent from the index simply counts zero.
COUNT_TYPES = (
    "tool", "capsule-definition", "playbook", "how-to",
    "session-agent", "action", "loop", "pipeline",
)
COUNT_LABELS = {
    "tool": "tools", "capsule-definition": "capsules", "playbook": "playbooks",
    "how-to": "skills", "session-agent": "session agents", "action": "actions",
    "loop": "loops", "pipeline": "pipelines",
}

#: The Review figures the Map embeds by reference (never redrawn, never
#: inlined: 01's own text names the studio it was drawn in). Captions are
#: read from the Review's Appendix A table at render time.
FIGURE_FILES = ("01-system-map", "02-capsule-type-system", "07-pipelines-and-loops", "10-write-path")

#: The root project every subsystem hub declares membership in. The visual is
#: generated from ITS members, so the diagram cannot drift from the substrate.
SUBSYSTEMS_ROOT_UID = "aae9a37b"

#: A hub may declare the folder it calls home; none does today, and the
#: contract's own fallback is the vault (AC8). Kept as an ordered key list so
#: the day a hub declares `subsystem_home: agents/` it moves band with no
#: code change here.
HOME_KEYS = ("subsystem_home", "home_folder")
DEFAULT_HOME = "vault/"

#: The three layers of the location contract (Studio Map §5), in the order a
#: reader meets them: the kernel underneath, the governed store in the middle,
#: the surfaces humans and agents touch on top.
BANDS = (
    ("kernel", "Kernel", (".tropo/", ".tropo-studio/")),
    ("primitives", "Primitives", ("vault/",)),
    ("apps", "Apps", ("agents/", "boards/", "docs/")),
)

FINGERPRINT_RE = re.compile(r"<!--\s*tropo:source-body-sha256:([0-9a-f]{64})\s*-->")
RENDER_FINGERPRINT_RE = re.compile(r"<!--\s*tropo:render-fingerprint:([0-9a-f]{64})\s*-->")
IDENTITY_REL = Path(".tropo") / "studio-identity.md"  # genesis-minted; absent pre-genesis and in every test fixture


class RenderInputError(Exception):
    """A declared input the render REQUIRES is missing or empty. Raised, never
    swallowed: AC8's whole point is that a resources section which quietly
    disappears is worse than a render that refuses and names the file."""


def studio_identity(root: Path) -> "dict[str, str] | None":
    """Design ruling s3 (f01564310146), 'data not structure': the ONE addition
    to the Map's seven sections is a header naming THIS studio -- entity_name,
    mint_prefix, genesis date -- read from .tropo/studio-identity.md at render
    time, so the first thing a new owner sees is their own studio's name.
    Returns None when the manifest is absent (a pre-genesis box, a fixture
    directory) -- the render then carries no header and never fails, because
    a render that refuses on a missing optional is a dead box on first boot."""
    path = Path(root) / IDENTITY_REL
    if not path.is_file():
        return None
    front, _body = _split_frontmatter(path.read_text(encoding="utf-8"))
    out: "dict[str, str]" = {}
    for key in ("entity_name", "mint_prefix", "created"):
        m = re.search(rf"^{key}:\s*'?\"?([^'\"\n]+)'?\"?\s*$", front, re.MULTILINE)
        if m:
            out[key] = m.group(1).strip()
    return out or None


def studio_header_html(identity: "dict[str, str] | None", box: bool = False) -> str:
    """`box=True` renders for a shipped box: the identity read is still the one
    found at --vault-path and NOWHERE else, so pointing --box at a build dir
    (which carries no manifest, AC1) yields the neutral header by construction
    rather than by a second rule. A box that shipped the builder's studio name
    in its Map header would be the exact defect AC1 exists to prevent."""
    if not identity:
        return (
            '<header class="studio-header">\n'
            "<p>This is the Studio Map for this studio.</p>\n"
            "</header>\n"
        ) if box else ""
    name = html.escape(identity.get("entity_name", ""), quote=False)
    prefix = html.escape(identity.get("mint_prefix", ""), quote=False)
    born = html.escape(identity.get("created", ""), quote=False)
    bits = [b for b in (
        f"<strong>{name}</strong>" if name else "",
        f"mint prefix <code>{prefix}</code>" if prefix else "",
        f"genesis {born}" if born else "",
    ) if b]
    return (
        '<header class="studio-header">\n'
        f"<p>This is the Studio Map for {' &middot; '.join(bits)}.</p>\n"
        "</header>\n"
    )

_BLOCK_START_RE = re.compile(r"^(#{1,6})\s|^---$|^\|")
_ABSOLUTE_HREF_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


#: Set by render() for a --box render and cleared after: the box root every
#: relative link is resolved against. A link whose target the box does not
#: carry renders as text, not as an anchor. Vela's AC8 read of the sealed
#: v1.95 candidate #2 (f0152975b448) found nine of 114 map links dead in the
#: box -- per-studio derivations, the withheld inbox uid, studio memory and
#: registries the box never ships -- because links were pure string math
#: over a source the box does not contain. A studio's own render (no --box)
#: is untouched: what the studio has, it links.
_BOX_LINK_ROOT: "Path | None" = None


def _box_target_exists(href: str, source_dir: str) -> bool:
    """True unless a --box render can see the link's target is absent."""
    if _BOX_LINK_ROOT is None or _ABSOLUTE_HREF_RE.match(href) or href.startswith("#"):
        return True
    path_part = href.partition("#")[0]
    if not path_part:
        return True
    repo_relative = posixpath.normpath(posixpath.join(source_dir, path_part))
    return (Path(_BOX_LINK_ROOT) / repo_relative).exists()


def _rewrite_href(href: str, source_dir: str, output_dir: str) -> str:
    """Rewrite a link written relative to SOURCE_DIR (docs/) into one
    relative to OUTPUT_DIR (boards/po/) -- carrying an href through
    unchanged silently breaks every relative link the moment source and
    output live in different directories, which they always do here.
    Pure string math (posixpath), never touches the filesystem, so it
    works the same whether or not the target actually exists yet."""
    if _ABSOLUTE_HREF_RE.match(href) or href.startswith("#"):
        return href  # absolute URL / mailto / same-page anchor
    path_part, hash_sep, fragment = href.partition("#")
    if not path_part:
        return href
    repo_relative = posixpath.normpath(posixpath.join(source_dir, path_part))
    rewritten = posixpath.relpath(repo_relative, output_dir)
    return rewritten + (hash_sep + fragment if hash_sep else "")


def body_sha256(path: Path) -> str:
    """Same hashing contract as tropo-validate.py's boot-derivation
    fingerprints (v1.70 S3.5.2): body = content after the closing
    frontmatter fence, normalized to exactly one trailing newline. Sharing
    the contract means the Map is fingerprinted the same way every other
    drift-gated source already is — AC5's staleness leg is this shape,
    not a new one."""
    raw = path.read_bytes()
    parts = raw.split(b"\n---\n", 1)
    body = parts[1] if len(parts) == 2 else raw
    body = body.rstrip(b"\n") + b"\n"
    return hashlib.sha256(body).hexdigest()


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[:end], text[end + 5 :]
    return "", text


def _inline(text: str, source_dir: str, output_dir: str) -> str:
    """Inline markdown -> HTML: links, bold, inline code. Escapes FIRST so
    no source byte can inject markup, then applies a fixed, small token
    set. Code spans are stashed before the bold/link passes run so
    `**not bold**` inside backticks is never touched. Every link href is
    rewritten from source-relative to output-relative (see _rewrite_href)."""
    text = html.escape(text, quote=False)
    stashed: list[str] = []

    def _stash(m: "re.Match[str]") -> str:
        stashed.append(m.group(1))
        return f"\x00CODE{len(stashed) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    def _link(m: "re.Match[str]") -> str:
        href = html.unescape(m.group(2))
        if not _box_target_exists(href, source_dir):
            return f'<span class="unshipped" title="not in this box">{m.group(1)}</span>'
        return (
            f'<a href="{html.escape(_rewrite_href(href, source_dir, output_dir), quote=True)}">'
            f"{m.group(1)}</a>"
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    for i, code in enumerate(stashed):
        text = text.replace(f"\x00CODE{i}\x00", f"<code>{code}</code>")
    return text


def render_body(markdown_body: str, source_dir: str, output_dir: str) -> str:
    """A small, deterministic markdown -> HTML pass covering exactly the
    constructs the Studio Map uses: headers, horizontal rules, GFM pipe
    tables, unordered lists, paragraphs. Not a general markdown engine —
    a derived render has no judgment to exercise about anything markdown
    CAN express, only about what THIS document actually does."""
    lines = markdown_body.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            close_list()
            i += 1
            continue

        if stripped == "---":
            close_list()
            out.append("<hr>")
            i += 1
            continue

        header_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if header_match:
            close_list()
            level = len(header_match.group(1))
            out.append(f"<h{level}>{_inline(header_match.group(2), source_dir, output_dir)}</h{level}>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and re.match(
            r"^\|?[\s:-]+\|", lines[i + 1].strip()
        ):
            close_list()
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2  # header row + separator row
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(
                    [c.strip() for c in lines[i].strip().strip("|").split("|")]
                )
                i += 1
            out.append(
                "<table><thead><tr>"
                + "".join(f"<th>{_inline(c, source_dir, output_dir)}</th>" for c in header_cells)
                + "</tr></thead><tbody>"
            )
            for row in rows:
                out.append(
                    "<tr>" + "".join(f"<td>{_inline(c, source_dir, output_dir)}</td>" for c in row) + "</tr>"
                )
            out.append("</tbody></table>")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(stripped[2:], source_dir, output_dir)}</li>")
            i += 1
            continue

        close_list()
        para_lines = [stripped]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not _BLOCK_START_RE.match(lines[i].strip())
            and not lines[i].strip().startswith(("- ", "* "))
        ):
            para_lines.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para_lines), source_dir, output_dir)}</p>")

    close_list()
    return "\n".join(out)


def read_index(root: Path) -> "list[dict]":
    """Every row of vault/00-index.jsonl, or [] when there is no index yet.
    A pre-genesis box has no index and a render that died on that would be a
    dead box on first boot — the same reasoning the identity read already
    follows. Malformed lines are skipped, never fatal: the index is a machine
    journal and one bad line must not cost a human their Map."""
    path = Path(root) / INDEX_REL
    if not path.is_file():
        return []
    rows: "list[dict]" = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _frontmatter_value(path: Path, keys: "tuple[str, ...]") -> "str | None":
    """The first of `keys` declared in a governed file's frontmatter, or None.
    Inline `# comments` after the value are stripped; quotes are stripped."""
    if not path.is_file():
        return None
    front, _body = _split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    for key in keys:
        m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", front, re.MULTILINE)
        if not m:
            continue
        value = m.group(1).split("#", 1)[0].strip().strip("'\"").strip()
        if value:
            return value
    return None


def read_subsystems(root: Path) -> "list[dict[str, str]]":
    """The subsystem list, READ FROM THE INDEX at render time: the projects
    that declare membership in the tropo-subsystems root. Sorted by title so
    the render — and the fingerprint over it — is deterministic.

    The home folder is read from the HUB FILE's frontmatter first (the
    governed source; v1.95 A5, measured by Metis G121: a full index rebuild
    does not project `subsystem_home`, so a row-only read ships a collapsed
    picture), then from the row, then the contract's fallback."""
    subs: "list[dict[str, str]]" = []
    for row in read_index(root):
        if row.get("type") != "project":
            continue
        if SUBSYSTEMS_ROOT_UID not in (row.get("member_of") or []):
            continue
        path = str(row.get("path") or f"vault/files/{row.get('uid')}.md")
        # File first, and ABSENT is the only reason to look at the row. The
        # first cut used DEFAULT_HOME as the absent sentinel, so a hub that
        # legitimately declares `vault/` (which IS the default) fell through to
        # the index row -- and on a clone whose row was written by --only before
        # the hub was re-homed, that row is stale (Metis G121 measured it
        # 2026-09-05: Tropo Work rendered in the apps band from a row that
        # said boards/ while its file said vault/). The file is the source; the
        # row is a fallback for the key's absence, never a tie-breaker.
        declared = _frontmatter_value(Path(root) / path, HOME_KEYS)
        if declared is None or not str(declared).strip():
            declared = None
            for key in HOME_KEYS:
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    declared = value.strip()
                    break
        home = str(declared).strip() if declared else DEFAULT_HOME
        subs.append(
            {
                "uid": str(row.get("uid", "")),
                "title": str(row.get("title", "")) or str(row.get("uid", "")),
                "home": home if home.endswith("/") else home + "/",
                "path": path,
            }
        )
    subs.sort(key=lambda s: (s["title"], s["uid"]))
    return subs


def subsystems_fingerprint(subsystems: "list[dict[str, str]]") -> str:
    """Hash of the sorted (uid, title, home) list — the render's third input.
    A hub added, renamed, dropped, or re-homed moves this hash and the render
    goes stale (home joined the hash at v1.95 A5: it is now read from the hub
    file, so a hub moving band must be visible to --check-stale)."""
    payload = "\n".join(f"{s['uid']}\t{s['title']}\t{s.get('home', '')}" for s in subsystems) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def band_of(home: str) -> str:
    """Which of the three layers a home folder belongs to. Unmatched homes
    fall to the primitives band, because the declared fallback home IS the
    vault and the vault is that band."""
    first = home.strip("/").split("/")[0] + "/"
    for key, _label, folders in BANDS:
        if first in folders:
            return key
    return "primitives"


VIZ_CSS = """
.studio-viz-wrap{margin:18px 0 26px;}
.studio-viz{--viz-surface:var(--tropo-surface,#FFFFFF);--viz-band:var(--tropo-ink05,#EDEBE5);
  --viz-line:var(--tropo-ink20,#C9CCD2);--viz-ink:var(--tropo-ink,#14181D);
  --viz-muted:var(--tropo-ink50,#6B7280);--viz-accent:var(--tropo-accent,#FF5E1A);
  --viz-box:var(--tropo-surface,#FFFFFF);
  display:block;width:100%;height:auto;border:1px solid var(--viz-line);border-radius:12px;}
@media (prefers-color-scheme: dark){
  .studio-viz{--viz-surface:#14181D;--viz-band:#1D232B;--viz-line:#3A4049;--viz-ink:#F4F2EC;
    --viz-muted:#9AA3AE;--viz-accent:#FF7A3D;--viz-box:#20262E;}
}
.studio-viz a text{text-decoration:none;}
.studio-viz a:hover .viz-box{stroke:var(--viz-accent);stroke-width:2;}
.viz-caption{color:var(--tropo-ink50,#6B7280);font-size:12px;margin-top:6px;}
.map-derived{margin:26px 0;}
.derived-caption{color:var(--tropo-ink50,#6B7280);font-size:12px;margin:2px 0 10px;}
.map-derived table{width:100%;border-collapse:collapse;font-size:13px;}
.map-derived th,.map-derived td{padding:6px 8px;border-bottom:1px solid var(--tropo-ink20,#C9CCD2);text-align:left;vertical-align:top;}
.map-derived th{font-size:12px;color:var(--tropo-ink50,#6B7280);font-weight:600;}
.map-derived td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
.map-derived .owns{font-size:12px;color:var(--tropo-ink50,#6B7280);}
.map-derived details{margin:8px 0;border:1px solid var(--tropo-ink20,#C9CCD2);border-radius:8px;padding:6px 10px;}
.map-derived summary{cursor:pointer;font-weight:600;}
.map-figures .fig-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:12px;}
.map-figures figure{margin:0;}
.map-figures img{width:100%;height:auto;border:1px solid var(--tropo-ink20,#C9CCD2);border-radius:10px;background:#fafbfc;}
.map-figures figcaption{font-size:12px;color:var(--tropo-ink50,#6B7280);margin-top:6px;}
"""


def svg_studio_visual(
    subsystems: "list[dict[str, str]]",
    output_dir: str = OUTPUT_REL.parent.as_posix(),
    counts: "dict[str, dict[str, int]] | None" = None,
) -> str:
    """A generated diagram of the studio: three bands (the location contract's
    layers), each subsystem a labeled box in the band its home belongs to,
    each box a link to that hub's governed file. Geometry is computed from the
    list — nothing about the nine is written down here — so the picture cannot
    lie about the substrate the way a hand-drawn one eventually does.

    v1.95 A5: when `counts` (from hub_counts) is given, each box carries a
    third line with its live counts, and the grid drops to two columns so the
    line fits without truncation."""
    if not subsystems:
        return ""
    width, pad, label_w, gap, box_h, row_gap, cols = 760, 14, 132, 14, 48, 12, 3
    if counts:
        box_h, cols = 64, 2
    x0 = pad + label_w + 12
    box_w = (width - pad - x0 - (cols - 1) * gap) // cols

    placed: "dict[str, list[dict[str, str]]]" = {key: [] for key, _l, _f in BANDS}
    for sub in subsystems:
        placed[band_of(sub["home"])].append(sub)

    layout, y = [], pad
    for key, label, folders in BANDS:
        members = placed[key]
        rows = max(1, (len(members) + cols - 1) // cols)
        height = 14 + rows * box_h + (rows - 1) * row_gap + 14 if members else 54
        layout.append((label, folders, members, y, height))
        y += height + 10
    total_h = y - 10 + pad

    esc = lambda s: html.escape(s, quote=False)  # noqa: E731
    out = [
        f'<svg class="studio-viz" viewBox="0 0 {width} {total_h}" '
        f'role="img" aria-labelledby="viz-title" xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">',
        f'<title id="viz-title">The studio in three layers: '
        f'{len(subsystems)} subsystems and the folders they call home</title>',
        f'<rect width="{width}" height="{total_h}" rx="12" fill="var(--viz-surface)"/>',
    ]
    for label, folders, members, band_y, band_h in layout:
        out.append(
            f'<rect x="{pad}" y="{band_y}" width="{width - 2 * pad}" height="{band_h}" '
            'rx="9" fill="var(--viz-band)" stroke="var(--viz-line)"/>'
        )
        out.append(
            f'<text x="{pad + 14}" y="{band_y + 25}" font-size="13" font-weight="600" '
            f'fill="var(--viz-ink)" font-family="var(--tropo-display, sans-serif)">{esc(label)}</text>'
        )
        out.append(
            f'<text x="{pad + 14}" y="{band_y + 42}" font-size="10.5" fill="var(--viz-muted)" '
            f'font-family="var(--tropo-mono, monospace)">{esc(" · ".join(folders))}</text>'
        )
        if not members:
            out.append(
                f'<text x="{x0}" y="{band_y + 32}" font-size="11.5" fill="var(--viz-muted)" '
                'font-style="italic">no subsystem declares a home here</text>'
            )
            continue
        for i, sub in enumerate(members):
            bx = x0 + (i % cols) * (box_w + gap)
            by = band_y + 14 + (i // cols) * (box_h + row_gap)
            href = html.escape(
                _rewrite_href(sub["path"], ".", output_dir), quote=True
            )
            title = sub["title"]
            title = title if len(title) <= 26 else title[:25] + "…"
            out.append(f'<a href="{href}" xlink:href="{href}">')
            out.append(
                f'<rect class="viz-box" x="{bx}" y="{by}" width="{box_w}" height="{box_h}" '
                'rx="7" fill="var(--viz-box)" stroke="var(--viz-line)"/>'
            )
            out.append(
                f'<text x="{bx + 11}" y="{by + 21}" font-size="12.5" font-weight="600" '
                f'fill="var(--viz-ink)" font-family="var(--tropo-display, sans-serif)">{esc(title)}</text>'
            )
            out.append(
                f'<text x="{bx + 11}" y="{by + 37}" font-size="10" fill="var(--viz-muted)" '
                f'font-family="var(--tropo-mono, monospace)">{esc(sub["home"])}</text>'
            )
            if counts:
                c = counts.get(sub["uid"], {})
                line = (
                    f"{int(c.get('tool', 0))} tools · {int(c.get('capsule-definition', 0))} capsules · "
                    f"{int(c.get('playbook', 0))} playbooks · {int(c.get('how-to', 0))} skills"
                )
                out.append(
                    f'<text x="{bx + 11}" y="{by + 53}" font-size="9.5" fill="var(--viz-muted)" '
                    f'font-family="var(--tropo-mono, monospace)">{esc(line)}</text>'
                )
            out.append("</a>")
    out.append("</svg>")
    counts_note = (
        "; the counts are the index's own subsystem_hub tags, read at render" if counts else ""
    )
    return (
        '<figure class="studio-viz-wrap">\n'
        + "\n".join(out)
        + '\n<figcaption class="viz-caption">Generated from the '
        f"{len(subsystems)} subsystem hubs in this studio's index — each box links to its hub{counts_note}."
        "</figcaption>\n</figure>\n"
    )


def resources_html(
    resources_path: Path,
    output_dir: str = OUTPUT_REL.parent.as_posix(),
) -> str:
    """The Resources section, rendered from the ONE declared file. Its links
    are written box-relative (from the Studio root) and rewritten here for the
    render's own directory, so the same file works in this studio and in an
    extracted box. Missing or link-less file: REFUSE. Mike asked for links to
    resources on the shipped HTML; a section that silently vanishes when
    someone moves the file is the failure mode, not the safe default."""
    path = Path(resources_path)
    if not path.is_file():
        raise RenderInputError(
            f"declared resources file missing at {path.as_posix()} — the Studio "
            "Map's Resources section is rendered from that ONE file; create it "
            "or fix the path, do not render without it"
        )
    _front, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    items = [
        line.strip()[2:]
        for line in body.split("\n")
        if line.strip().startswith("- ") and "](" in line
    ]
    if not items:
        raise RenderInputError(
            f"declared resources file {path.as_posix()} carries no "
            "`- [Title](link) — why` lines; a Resources section with nothing in "
            "it is a silent omission wearing a heading"
        )
    lis = "\n".join(f"<li>{_inline(item, '.', output_dir)}</li>" for item in items)
    return (
        '<section class="map-resources">\n<h2>Resources</h2>\n'
        f"<ul>\n{lis}\n</ul>\n</section>\n"
    )


def _agent_homes(root: Path) -> "list[tuple[str, str]]":
    """(slug, link target) for every agents/<slug>/ that has a charter — either
    a charter file of its own or an activation that names one by uid. The
    activation is what a reader actually opens, so that is what we link."""
    found: "list[tuple[str, str]]" = []
    agents_dir = Path(root) / "agents"
    if not agents_dir.is_dir():
        return found
    for entry in sorted(p for p in agents_dir.iterdir() if p.is_dir()):
        slug = entry.name
        charter_files = sorted(entry.glob("*charter*.md"))
        activation = entry / f"{slug}-activation.md"
        has_activation_charter = False
        if activation.is_file():
            head = activation.read_text(encoding="utf-8", errors="replace")[:4000]
            has_activation_charter = "charter" in head.lower()
        if not charter_files and not has_activation_charter:
            continue
        if activation.is_file():
            target = f"agents/{slug}/{activation.name}"
        else:
            target = f"agents/{slug}/{charter_files[0].name}"
        found.append((slug, target))
    return found


def overlay_html(
    studio_root: Path,
    output_dir: str = OUTPUT_REL.parent.as_posix(),
) -> str:
    """`--overlay`: a live "This studio" section derived from the studio's own
    index and folders — its agents, its open projects, its boards. Never
    rendered into a box (a box has no customer studio yet) and never
    fingerprinted: this is live state, not a source the render derives from,
    and gating staleness on it would make every render stale by lunchtime."""
    root = Path(studio_root)
    parts: "list[str]" = []

    agents = _agent_homes(root)
    if agents:
        links = "\n".join(
            f'<li><a href="{html.escape(_rewrite_href(target, ".", output_dir), quote=True)}">'
            f"{html.escape(slug, quote=False)}</a></li>"
            for slug, target in agents
        )
        parts.append(f"<h3>Agents</h3>\n<ul>\n{links}\n</ul>")

    rows = read_index(root)
    projects = [
        r
        for r in rows
        if r.get("type") == "project" and r.get("status") in ("active", "new")
    ]
    projects.sort(key=lambda r: (str(r.get("modified") or ""), str(r.get("uid"))), reverse=True)
    if projects:
        links = "\n".join(
            '<li><a href="{href}">{title}</a> <code>{status}</code></li>'.format(
                href=html.escape(
                    _rewrite_href(
                        str(r.get("path") or f"vault/files/{r.get('uid')}.md"),
                        ".",
                        output_dir,
                    ),
                    quote=True,
                ),
                title=html.escape(str(r.get("title") or r.get("uid")), quote=False),
                status=html.escape(str(r.get("status")), quote=False),
            )
            for r in projects[:20]
        )
        parts.append(f"<h3>Projects</h3>\n<ul>\n{links}\n</ul>")

    boards_dir = root / "boards"
    boards: "list[str]" = []
    if boards_dir.is_dir():
        for owner in sorted(p for p in boards_dir.iterdir() if p.is_dir()):
            if owner.name.startswith("_"):
                continue
            for board in sorted(owner.glob("*.html")):
                rel = f"boards/{owner.name}/{board.name}"
                if rel == OUTPUT_REL.as_posix():
                    continue  # the Map does not link to itself
                boards.append(rel)
    if boards:
        links = "\n".join(
            f'<li><a href="{html.escape(_rewrite_href(rel, ".", output_dir), quote=True)}">'
            f"{html.escape(rel, quote=False)}</a></li>"
            for rel in boards
        )
        parts.append(f"<h3>Boards</h3>\n<ul>\n{links}\n</ul>")

    if not parts:
        return ""
    return (
        '<section class="this-studio">\n<h2>This studio</h2>\n'
        + "\n".join(parts)
        + "\n</section>\n"
    )


# ---------------------------------------------------------------------------
# v1.95 A5 — the derived sections. Every function below READS a source at
# render time and returns plain data; nothing about the nine, the types, or the
# rules is written in this file. An absent source returns empty and the section
# it feeds is simply not rendered (warn-safe, deb77758): a box missing a crew
# brief is a box on its first day, not a broken one.
# ---------------------------------------------------------------------------


def _hubs_of(row: dict) -> "list[str]":
    value = row.get("subsystem_hub")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def hub_counts(rows: "list[dict]", subsystems: "list[dict[str, str]]") -> "dict[str, dict[str, int]]":
    """Per hub uid, how many index rows of each COUNT_TYPES type declare that
    hub in their `subsystem_hub` frontmatter. The index is the source; the
    catalogs are its render, so this is the same count the catalogs show."""
    counts: "dict[str, dict[str, int]]" = {s["uid"]: {t: 0 for t in COUNT_TYPES} for s in subsystems}
    for row in rows:
        kind = row.get("type")
        if kind not in COUNT_TYPES:
            continue
        for hub in _hubs_of(row):
            if hub in counts:
                counts[hub][kind] += 1
    return counts


def _version_key(version: str) -> "tuple[int, ...]":
    return tuple(int(p) for p in re.findall(r"\d+", str(version)))


def registry_last_release(root: Path) -> "dict[str, str]":
    """The last release that touched each subsystem, from the per-release
    touch-record registry (.tropo-studio/registries/subsystem-registry.jsonl):
    the highest release_version per subsystem_uid. {} when absent."""
    path = Path(root) / REGISTRY_REL
    if not path.is_file():
        return {}
    last: "dict[str, str]" = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        uid = str(row.get("subsystem_uid") or "")
        version = str(row.get("release_version") or "")
        if not uid or not version:
            continue
        if uid not in last or _version_key(version) > _version_key(last[uid]):
            last[uid] = version
    return last


def capsule_rows(rows: "list[dict]") -> "list[dict]":
    """Every capsule-definition row of the index: the governed types that
    exist, with the subsystem each declares. Sorted by title so the render and
    its fingerprint are deterministic."""
    out: "list[dict]" = []
    for row in rows:
        if row.get("type") != "capsule-definition":
            continue
        uid = str(row.get("uid") or "")
        out.append(
            {
                "uid": uid,
                "title": str(row.get("title") or uid),
                "description": str(row.get("description") or ""),
                "version": str(row.get("version") or ""),
                "hubs": _hubs_of(row),
                "path": str(row.get("path") or f"vault/files/{uid}.md"),
            }
        )
    out.sort(key=lambda r: (r["title"].lower(), r["uid"]))
    return out


_NUMBERED_BOLD_RE = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(.*)$")


def _section_lines(text: str, heading_prefix: str) -> "list[str]":
    """The lines under the first `## ` heading whose text starts with
    heading_prefix, up to the next `## ` heading."""
    out: "list[str]" = []
    inside = False
    for line in text.split("\n"):
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().startswith(heading_prefix)
            continue
        if inside:
            out.append(line)
    return out


def kernel_invariants(root: Path) -> "list[dict]":
    """The OS-level invariants, parsed from TROPO-CONTROL.md section 3: the
    numbered `N. **Title.** text` items. [] when the file is absent."""
    path = Path(root) / CONTROL_REL
    if not path.is_file():
        return []
    items: "list[dict]" = []
    for line in _section_lines(path.read_text(encoding="utf-8"), "3. OS-Level Invariants"):
        m = _NUMBERED_BOLD_RE.match(line.strip())
        if m:
            items.append({"number": m.group(1), "title": m.group(2).strip().rstrip("."), "text": m.group(3).strip()})
    return items


def operating_principles(root: Path) -> "list[dict]":
    """The Operating Principle titles, parsed from the boot digest's numbered
    list (the digest is the fingerprinted compression every agent reads at
    boot). [] when absent."""
    path = Path(root) / DIGEST_REL
    if not path.is_file():
        return []
    items: "list[dict]" = []
    for line in _section_lines(path.read_text(encoding="utf-8"), "The 15 Operating Principles"):
        m = _NUMBERED_BOLD_RE.match(line.strip())
        if m:
            items.append({"number": int(m.group(1)), "title": m.group(2).strip()})
    return items


def studio_version(root: Path) -> "str | None":
    path = Path(root) / VERSION_REL
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return line.strip()
    return None


def review_figures(root: Path) -> "list[dict]":
    """The Review figures the Map embeds by reference, with their captions
    READ from the Review's Appendix A diagram index. Only figures whose svg
    is actually on disk are returned, so a caption never points at nothing."""
    path = Path(root) / REVIEW_REL
    if not path.is_file():
        return []
    figs: "list[dict]" = []
    for line in _section_lines(path.read_text(encoding="utf-8"), "Appendix A"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.search(r"svg/([0-9]{2}-[a-z0-9-]+)\.svg", cells[0])
        if not m or m.group(1) not in FIGURE_FILES:
            continue
        rel = REVIEW_REL.parent / "svg" / f"{m.group(1)}.svg"
        if not (Path(root) / rel).is_file():
            continue
        figs.append({"file": f"{m.group(1)}.svg", "caption": cells[1], "path": rel.as_posix()})
    figs.sort(key=lambda f: f["file"])
    return figs


L1_ENTRY_REL = Path("vault") / "files" / "eca73d77.md"
_UID_RE = re.compile(r"\b([0-9a-f]{8}(?:[0-9a-f]{4})?)\b")


def l1_owns(root: Path) -> "dict[str, str]":
    """What each subsystem owns, in one clause, READ from the L1 canonical
    entry's section 5 table (`| # | Subsystem | UID | What it owns |`) at
    render time, keyed by the hub uid in the third column. The L1 entry is a
    governed kb-article that ships in the box. {} when absent."""
    path = Path(root) / L1_ENTRY_REL
    if not path.is_file():
        return {}
    out: "dict[str, str]" = {}
    for line in _section_lines(path.read_text(encoding="utf-8"), "§5"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        m = _UID_RE.search(cells[2])
        if not m or set(cells[3]) <= set("-: "):
            continue
        owns = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cells[3])  # links -> text
        owns = owns.replace("**", "").replace("`", "").strip()  # keep `sa.*` intact
        if owns:
            out[m.group(1)] = owns
    return out


def review_capsule_line(root: Path) -> str:
    """What a capsule IS, in the Review's own words: the opening sentences of
    section 3.1 ("Capsules: schema as governed markdown"), read at render, up
    to and including the first sentence that names the word. The stranger
    cold-read (V2) missed exactly this question; the answer exists in the
    canonical document, so the render carries it from there, not from here."""
    path = Path(root) / REVIEW_REL
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^###\s+3\.1\b", line):
            for para in lines[i + 1 :]:
                if para.strip():
                    sentences = re.split(r"(?<=\.)\s+", para.strip())
                    keep: "list[str]" = []
                    for s in sentences:
                        keep.append(s)
                        if "capsule" in s.lower():
                            break
                    # single-asterisk emphasis is markdown the inline pass does
                    # not render; the words stay, the markers go
                    return re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", " ".join(keep))
            break
    return ""


def _owns_for(uid: str, owns_map: "dict[str, str]") -> str:
    return owns_map.get(uid, "")


def crew_active_table(root: Path) -> "tuple[list[str], list[list[str]]] | None":
    """The crew brief's operating table: the FIRST pipe table between the
    crew-table markers. None when the brief or the markers are absent."""
    path = Path(root) / CREW_BRIEF_REL
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    start = text.find("<!-- crew-table:start -->")
    end = text.find("<!-- crew-table:end -->")
    if start == -1 or end == -1 or end < start:
        return None
    block = text[start:end].split("\n")
    i = 0
    while i < len(block):
        stripped = block[i].strip()
        if stripped.startswith("|") and i + 1 < len(block) and re.match(r"^\|?[\s:-]+\|", block[i + 1].strip()):
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: "list[list[str]]" = []
            while i < len(block) and block[i].strip().startswith("|"):
                rows.append([c.strip() for c in block[i].strip().strip("|").split("|")])
                i += 1
            return headers, rows
        i += 1
    return None


def _hash_rows(rows) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _caption(text: str) -> str:
    return f'<p class="derived-caption"><em>derived from {html.escape(text, quote=False)} at render; nothing in this section is hand-written</em></p>\n'


def subsystems_html(
    subsystems: "list[dict[str, str]]",
    counts: "dict[str, dict[str, int]]",
    last_release: "dict[str, str]",
    owns_map: "dict[str, str]",
    output_dir: str,
    box: bool = False,
) -> str:
    if not subsystems:
        return ""
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    head = "".join(f"<th>{esc(COUNT_LABELS[t])}</th>" for t in COUNT_TYPES)
    rows: "list[str]" = []
    for sub in subsystems:
        href = html.escape(_rewrite_href(sub["path"], ".", output_dir), quote=True)
        c = counts.get(sub["uid"], {})
        owns = _owns_for(sub["uid"], owns_map)
        cells = "".join(f'<td class="num">{int(c.get(t, 0))}</td>' for t in COUNT_TYPES)
        rows.append(
            f'<tr><td><a href="{href}"><strong>{esc(sub["title"])}</strong></a>'
            + (f'<br><span class="owns">{esc(owns)}</span>' if owns else "")
            + f'</td><td><code>{esc(sub["home"])}</code></td>{cells}'
            + f'<td>{esc(last_release.get(sub["uid"], "none recorded"))}</td></tr>'
        )
    sources = (
        f"vault/00-index.jsonl (the {len(subsystems)} hubs and every row's subsystem_hub tag"
        + ("; a shipped box counts only what it ships" if box else "")
        + "), each hub's own frontmatter (its home), "
        f"{REGISTRY_REL.as_posix()} (the last release that touched each)"
        + (f", and {L1_ENTRY_REL.as_posix()} section 5 (what each owns)" if owns_map else "")
    )
    return (
        '<section class="map-derived map-subsystems">\n'
        f"<h2>The {len(subsystems)} subsystems</h2>\n"
        + _caption(sources)
        + f"<table><thead><tr><th>Subsystem</th><th>Home</th>{head}<th>Last release that touched it</th></tr></thead>"
        + "<tbody>" + "".join(rows) + "</tbody></table>\n</section>\n"
    )


def types_html(
    capsules: "list[dict]",
    subsystems: "list[dict[str, str]]",
    output_dir: str,
    intro: str = "",
    root: "Path | None" = None,
) -> str:
    if not capsules:
        return ""
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    intro_html = ""
    if intro:
        review_rel = REVIEW_HTML_REL if root is not None and (Path(root) / REVIEW_HTML_REL).is_file() else REVIEW_REL
        review_href = html.escape(_rewrite_href(review_rel.as_posix(), ".", output_dir), quote=True)
        intro_html = (
            f'<p class="types-intro">{_inline(intro, REVIEW_REL.parent.as_posix(), output_dir)} '
            f'<a href="{review_href}">(the Architecture Review, section 3.1)</a></p>\n'
        )
    by_hub: "dict[str, list[dict]]" = {s["uid"]: [] for s in subsystems}
    unassigned: "list[dict]" = []
    for cap in capsules:
        homes = [h for h in cap["hubs"] if h in by_hub]
        (by_hub[homes[0]] if homes else unassigned).append(cap)

    def block(label: str, items: "list[dict]") -> str:
        body = "".join(
            f'<tr><td><a href="{html.escape(_rewrite_href(c["path"], ".", output_dir), quote=True)}">'
            f'{esc(c["title"])}</a></td><td><code>{esc(c["version"])}</code></td><td>{esc(c["description"])}</td></tr>'
            for c in items
        )
        noun = "governed type" if len(items) == 1 else "governed types"
        return (
            f"<details><summary>{esc(label)} · {len(items)} {noun}</summary>\n"
            "<table><thead><tr><th>Capsule</th><th>Version</th><th>What it governs</th></tr></thead>"
            f"<tbody>{body}</tbody></table></details>\n"
        )

    parts = [block(s["title"], by_hub[s["uid"]]) for s in subsystems if by_hub[s["uid"]]]
    if unassigned:
        parts.append(block("Unassigned (no subsystem_hub declared)", unassigned))
    return (
        '<section class="map-derived map-types">\n<h2>The governed types</h2>\n'
        + _caption(
            f"the {len(capsules)} capsule-definition rows of vault/00-index.jsonl; a capsule "
            "declares its subsystem in its own frontmatter"
            + ("; the definition of a capsule is the Review's section 3.1" if intro else "")
        )
        + intro_html
        + "".join(parts)
        + "</section>\n"
    )


def rules_html(
    invariants: "list[dict]",
    principles: "list[dict]",
    root: "Path | None",
    output_dir: str,
) -> str:
    if not invariants and not principles:
        return ""
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    parts: "list[str]" = []
    if invariants:
        href = html.escape(_rewrite_href(CONTROL_REL.as_posix(), ".", output_dir), quote=True)
        lis = []
        for inv in invariants:
            first = re.split(r"(?<=\.)\s", inv["text"], 1)[0]
            lis.append(
                f'<li value="{esc(inv["number"])}"><a href="{href}"><strong>{esc(inv["title"])}</strong></a> '
                f"{_inline(first, CONTROL_REL.parent.as_posix(), output_dir)}</li>"
            )
        parts.append(
            f'<h3>OS-level invariants (<a href="{href}">TROPO-CONTROL.md</a>, section 3; they override everything)</h3>\n'
            "<ol>" + "".join(lis) + "</ol>\n"
        )
    if principles:
        digest_href = html.escape(_rewrite_href(DIGEST_REL.as_posix(), ".", output_dir), quote=True)
        full_rel = PRINCIPLES_REL.as_posix()
        has_full = root is not None and (Path(root) / PRINCIPLES_REL).is_file()
        target = html.escape(_rewrite_href(full_rel if has_full else DIGEST_REL.as_posix(), ".", output_dir), quote=True)
        lis = "".join(
            f'<li value="{int(p["number"])}"><a href="{target}">{esc(p["title"])}</a></li>' for p in principles
        )
        full_link = f' · <a href="{target}">full text</a>' if has_full else ""
        parts.append(
            f'<h3>The {len(principles)} Operating Principles (<a href="{digest_href}">boot digest</a>{full_link})</h3>\n'
            "<ol>" + lis + "</ol>\n"
        )
    return (
        '<section class="map-derived map-rules">\n<h2>The rules that bind</h2>\n'
        + _caption(f"{CONTROL_REL.as_posix()} section 3 and {DIGEST_REL.as_posix()}; the law lives at the links")
        + "".join(parts)
        + "</section>\n"
    )


def work_html(
    version: "str | None",
    crew: "tuple[list[str], list[list[str]]] | None",
    box: bool,
    output_dir: str,
) -> str:
    show_crew = crew is not None and not box
    if version is None and not show_crew:
        return ""
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    parts: "list[str]" = []
    if version:
        vhref = html.escape(_rewrite_href(VERSION_REL.as_posix(), ".", output_dir), quote=True)
        parts.append(
            f'<p>This studio is at <strong>{esc(version)}</strong> '
            f'(<a href="{vhref}">{esc(VERSION_REL.as_posix())}</a>).</p>\n'
        )
    if show_crew:
        headers, rows = crew
        bhref = html.escape(_rewrite_href(CREW_BRIEF_REL.as_posix(), ".", output_dir), quote=True)
        head = "".join(f"<th>{_inline(h, '.', output_dir)}</th>" for h in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{_inline(c, '.', output_dir)}</td>" for c in row) + "</tr>" for row in rows
        )
        parts.append(
            f'<h3>Operating crew (<a href="{bhref}">00-crew-brief</a>)</h3>\n'
            f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>\n"
        )
    sources = VERSION_REL.as_posix() if version else ""
    if show_crew:
        sources += (" and " if sources else "") + f"{CREW_BRIEF_REL.as_posix()} (live state, read at render, not fingerprinted)"
    return '<section class="map-derived map-work">\n<h2>Where the work is</h2>\n' + _caption(sources) + "".join(parts) + "</section>\n"


def figures_html(figs: "list[dict]", root: "Path | None", output_dir: str) -> str:
    if not figs:
        return ""
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    review_rel = REVIEW_HTML_REL if root is not None and (Path(root) / REVIEW_HTML_REL).is_file() else REVIEW_REL
    review_href = html.escape(_rewrite_href(review_rel.as_posix(), ".", output_dir), quote=True)

    def fig(f: dict, cls: str) -> str:
        src = html.escape(_rewrite_href(f["path"], ".", output_dir), quote=True)
        return (
            f'<figure class="{cls}"><a href="{review_href}"><img src="{src}" alt="{html.escape(f["caption"], quote=True)}" loading="lazy"></a>'
            f'<figcaption>{esc(f["caption"])} · <a href="{review_href}">the Architecture Review</a></figcaption></figure>'
        )

    wide = [f for f in figs if f["file"].startswith("01-")]
    small = [f for f in figs if not f["file"].startswith("01-")]
    parts = [fig(f, "fig-wide") for f in wide]
    if small:
        parts.append('<div class="fig-grid">' + "".join(fig(f, "fig-small") for f in small) + "</div>")
    return (
        '<section class="map-derived map-figures">\n<h2>The system, drawn</h2>\n'
        + _caption("the Review's Appendix A (the captions) and its svg/ folder (the figures, embedded by reference, never redrawn)")
        + "".join(parts)
        + "</section>\n"
    )


def derived_sections_html(
    root: Path,
    rows: "list[dict]",
    subsystems: "list[dict[str, str]]",
    counts: "dict[str, dict[str, int]]",
    output_dir: str,
    box: bool,
) -> "dict[str, str]":
    """Every derived section's HTML, keyed by name, so render() can place them
    around the Map body in reading order."""
    return {
        "figures": figures_html(review_figures(root), root, output_dir),
        "subsystems": subsystems_html(subsystems, counts, registry_last_release(root), l1_owns(root), output_dir, box),
        "types": types_html(capsule_rows(rows), subsystems, output_dir, review_capsule_line(root), root),
        "rules": rules_html(kernel_invariants(root), operating_principles(root), root, output_dir),
        "work": work_html(studio_version(root), crew_active_table(root), box, output_dir),
    }


def fingerprint_inputs(
    source_path: Path,
    resources_path: "Path | None",
    subsystems: "list[dict[str, str]] | None",
    root: "Path | None" = None,
) -> "list[tuple[str, str]]":
    """(label, sha256) for every input this render reads, in a fixed order.
    AC8: 'the fingerprint extends to every new input' — the Map alone stopped
    being the whole answer the moment the render gained two more sources.

    v1.95 A5: with `root`, the derived sections' sources join the list. File
    inputs hash their body (one changed character flips them); index-derived
    inputs hash the rows the render actually shows, the same shape the
    subsystems entry already has. An absent source contributes no entry, the
    same way it renders no section. The crew brief is live state and is NOT
    here, for the reason the overlay gives."""
    inputs = [(SOURCE_REL.as_posix(), body_sha256(source_path))]
    if resources_path is not None:
        inputs.append((RESOURCES_REL.as_posix(), body_sha256(Path(resources_path))))
    if subsystems is not None:
        inputs.append(
            (
                f"subsystems@{INDEX_REL.as_posix()}[{len(subsystems)}]",
                subsystems_fingerprint(subsystems),
            )
        )
    if root is not None:
        root = Path(root)
        rows = read_index(root)
        if subsystems:
            inputs.append((f"hub-counts@{INDEX_REL.as_posix()}", _hash_rows(hub_counts(rows, subsystems))))
        caps = capsule_rows(rows)
        if caps:
            inputs.append((f"capsules@{INDEX_REL.as_posix()}[{len(caps)}]", _hash_rows(caps)))
        for rel in (REGISTRY_REL, CONTROL_REL, DIGEST_REL, VERSION_REL):
            path = root / rel
            if path.is_file():
                inputs.append((rel.as_posix(), body_sha256(path)))
        figs = review_figures(root)
        if figs:
            inputs.append((f"review-figures@{REVIEW_REL.as_posix()}", _hash_rows(figs)))
        capsule_line = review_capsule_line(root)
        if capsule_line:
            inputs.append((f"capsule-definition@{REVIEW_REL.as_posix()}", _hash_rows(capsule_line)))
        owns = l1_owns(root)
        if owns:
            inputs.append((f"eca73d77-s5@{L1_ENTRY_REL.as_posix()}", _hash_rows(owns)))
    return inputs


def composite_fingerprint(inputs: "list[tuple[str, str]]") -> str:
    payload = "\n".join(f"{label} {digest}" for label, digest in inputs) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render(
    source_path: Path,
    source_dir: str = SOURCE_REL.parent.as_posix(),
    output_dir: str = OUTPUT_REL.parent.as_posix(),
    root: "Path | None" = None,
    box: bool = False,
    overlay_root: "Path | None" = None,
) -> str:
    # `root` is optional so every existing caller and fixture keeps working;
    # only a caller that passes it gets the studio header (ruling s3), the
    # generated visual, and the Resources section. A rootless call renders
    # exactly what it always did.
    global _BOX_LINK_ROOT
    _BOX_LINK_ROOT = Path(root) if (box and root is not None) else None
    try:
        return _render(source_path, source_dir, output_dir, root, box, overlay_root)
    finally:
        _BOX_LINK_ROOT = None


def _render(
    source_path: Path,
    source_dir: str,
    output_dir: str,
    root: "Path | None",
    box: bool,
    overlay_root: "Path | None",
) -> str:
    header_html = (
        studio_header_html(studio_identity(root), box=box) if root is not None else ""
    )
    subsystems = read_subsystems(root) if root is not None else None
    resources_path = (Path(root) / RESOURCES_REL) if root is not None else None
    rows = read_index(root) if root is not None else []
    counts = hub_counts(rows, subsystems) if subsystems else {}
    visual_html = svg_studio_visual(subsystems, output_dir, counts or None) if subsystems else ""
    section_html = resources_html(resources_path, output_dir) if resources_path else ""
    derived = (
        derived_sections_html(Path(root), rows, subsystems or [], counts, output_dir, box)
        if root is not None
        else {}
    )
    overlay_section = ""
    if overlay_root is not None and not box:
        overlay_section = overlay_html(overlay_root, output_dir)

    text = source_path.read_text(encoding="utf-8")
    frontmatter_text, body_text = _split_frontmatter(text)
    title_match = re.search(
        r'^title:\s*"?(.+?)"?\s*$', frontmatter_text, re.MULTILINE
    )
    title = title_match.group(1) if title_match else "The Studio Map"
    # v1.95 A5 accuracy plan: every hand-written row carries an as-of date the
    # render prints. The Map declares it once in frontmatter (`as_of`,
    # `as_of_release`); a Map without it renders no claim rather than a
    # fabricated one.
    asof_match = re.search(r"""^as_of:\s*['"]?(\d{4}-\d{2}-\d{2})""", frontmatter_text, re.MULTILINE)
    asof_rel_match = re.search(r"""^as_of_release:\s*['"]?([0-9][0-9.]*)""", frontmatter_text, re.MULTILINE)
    asof_html = ""
    if asof_match:
        asof_release = f" (v{asof_rel_match.group(1)})" if asof_rel_match else ""
        asof_html = (
            '<p class="map-asof"><em>Hand-written rows verified against the studio tree as of '
            f"{html.escape(asof_match.group(1))}{html.escape(asof_release)}; the layers picture and the "
            "resources section are derived at render time.</em></p>\n"
        )
    fingerprint = body_sha256(source_path)
    inputs = fingerprint_inputs(source_path, resources_path, subsystems, root=root)
    composite = composite_fingerprint(inputs)
    inputs_comment = "\n".join(f"     {label} {digest}" for label, digest in inputs)
    body_html = render_body(body_text, source_dir, output_dir)
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title, quote=False)}</title>
<link rel="stylesheet" href="{STYLESHEET_HREF}">
<style>{VIZ_CSS}</style>
<!-- tropo:derived-render — regenerate with vault/tools/tropo-render-studio-map.py, never hand-edit -->
<!-- tropo:source-body-sha256:{fingerprint} -->
<!-- tropo:render-fingerprint:{composite} -->
<!-- tropo:render-inputs:
{inputs_comment}
-->
</head>
<body>
<div class="wrap">
{header_html}{section_html}{visual_html}{derived.get("figures", "")}{asof_html}{derived.get("subsystems", "")}{body_html}
{derived.get("types", "")}{derived.get("rules", "")}{derived.get("work", "")}{overlay_section}</div>
</body>
</html>
"""
    if box and root is not None:
        # A box must carry no path from the machine that built it. Cheap,
        # loud, and checked on the artifact itself rather than trusted.
        for absolute in {str(Path(root).resolve()), str(Path(root))}:
            if absolute not in (".", "") and absolute in document:
                raise RenderInputError(
                    f"--box render embedded an absolute path from this machine "
                    f"({absolute}); a shipped box must carry none"
                )
    return document


def check_staleness(
    rendered_path: Path,
    source_path: Path,
    resources_path: "Path | None" = None,
    subsystems: "list[dict[str, str]] | None" = None,
    root: "Path | None" = None,
) -> tuple[bool, str, str]:
    """(is_stale, rendered_fingerprint, current_fingerprint). Reads the
    fingerprint embedded in the last render and compares it to the CURRENT
    hash of every input the render reads — detectable by anything that runs
    this, never only by someone choosing to re-render (AC5's staleness leg).

    A render carrying the composite fingerprint is checked against every
    input; one carrying only the Map's body-sha256 (a rootless render, or one
    from before AC8) is checked against the Map alone, so the older artifact
    still gets the older, honest answer instead of a spurious STALE."""
    text = rendered_path.read_text(encoding="utf-8")
    composite_match = RENDER_FINGERPRINT_RE.search(text)
    if composite_match is not None:
        rendered_fp = composite_match.group(1)
        current_fp = composite_fingerprint(
            fingerprint_inputs(source_path, resources_path, subsystems, root=root)
        )
        return rendered_fp != current_fp, rendered_fp, current_fp
    match = FINGERPRINT_RE.search(text)
    if not match:
        raise ValueError(
            f"{rendered_path}: no tropo:source-body-sha256 fingerprint found"
        )
    rendered_fp = match.group(1)
    current_fp = body_sha256(source_path)
    return rendered_fp != current_fp, rendered_fp, current_fp


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-path", default=".")
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="Exit 1 and print both fingerprints if the rendered output is "
        "stale relative to ANY input it was rendered from (the Map, the "
        "resources file, the subsystem list); exit 0 and print FRESH "
        "otherwise. Does not render.",
    )
    parser.add_argument(
        "--box",
        action="store_true",
        help="Render for a shipped box rather than for this studio: the "
        "header carries only the identity found at --vault-path (a box has "
        "none, so it reads neutrally), the 'This studio' overlay is omitted, "
        "and no absolute path from this machine may appear in the output.",
    )
    parser.add_argument(
        "--overlay",
        nargs="?",
        const="",
        default=None,
        metavar="STUDIO_PATH",
        help="Append a live 'This studio' section (agents, open projects, "
        "boards) derived from that studio's index; defaults to --vault-path. "
        "Ignored under --box.",
    )
    args = parser.parse_args(argv)
    root = Path(args.vault_path).resolve()
    source_path = root / SOURCE_REL
    output_path = root / OUTPUT_REL
    resources_path = root / RESOURCES_REL

    if args.check_stale:
        if not output_path.is_file():
            print(f"REFUSAL: no rendered map at {output_path} to check", file=sys.stderr)
            return 1
        if not resources_path.is_file():
            print(
                f"REFUSAL: declared resources file missing at {resources_path} — "
                "the render reads it, so staleness cannot be judged without it",
                file=sys.stderr,
            )
            return 1
        is_stale, rendered_fp, current_fp = check_staleness(
            output_path, source_path, resources_path, read_subsystems(root), root=root
        )
        if is_stale:
            print(
                f"STALE: {output_path} was rendered from {rendered_fp} but its "
                f"inputs now hash to {current_fp}. Re-render with "
                "tropo-render-studio-map.py.",
                file=sys.stderr,
            )
            return 1
        print(f"FRESH: {output_path} matches its inputs ({current_fp})")
        return 0

    if not source_path.is_file():
        print(f"REFUSAL: canonical Studio Map missing at {source_path}", file=sys.stderr)
        return 1
    overlay_root: "Path | None" = None
    if args.overlay is not None and not args.box:
        overlay_root = Path(args.overlay).resolve() if args.overlay else root
    try:
        document = render(
            source_path, root=root, box=args.box, overlay_root=overlay_root
        )
    except RenderInputError as exc:
        print(f"REFUSAL: {exc}", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    print(f"Rendered {source_path} -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
