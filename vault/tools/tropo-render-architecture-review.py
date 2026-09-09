#!/usr/bin/env python3
"""Render the Architecture Review to a single self-contained HTML page.

WHY THIS EXISTS AS A TOOL AND NOT A HAND-WRITTEN FILE
    The v4 review's HTML was hand-authored. Nothing regenerated it, so it could
    not drift-check against its own markdown, and the two could disagree
    silently -- one fact, two readers, which is the studio's dominant defect
    family. v5's HTML is generated from the markdown, inlines its diagrams, and
    carries a fingerprint over every input so `--check-stale` fails loud.

WHAT IT DOES
    Markdown -> one HTML file: a sticky table of contents built from the
    headings, the SVG diagrams inlined at the sections that reference them (no
    external files, so the page travels as a single artifact), and the
    document's own measurement stamp carried onto the page.

    The markdown remains canonical. This is a rendering, and it says so.

USAGE
    python3 vault/tools/tropo-render-architecture-review.py
    python3 vault/tools/tropo-render-architecture-review.py --check-stale

Written by orpheus-o39, 2026-09-08. Sibling of tropo-render-systems-explorer.py
and tropo-render-studio-map.py, whose fingerprint contract it follows.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

SRC = "docs/architecture-review-v5/tropo-l1-architecture-review.md"
SVG_DIR = "docs/architecture-review-v5/svg"
V4_SVG_DIR = "docs/architecture-review-v4/svg"  # retained for the "v4" key; no diagram uses it now
OUT = "docs/architecture-review-v5/tropo-l1-architecture-review.html"
MARKER = "<!-- fingerprints:"

# Which diagram belongs under which section heading number. Every diagram now
# resolves inside v5's own svg/ folder -- including the five carried unchanged
# from v4, which were COPIED there rather than referenced across version folders
# (2026-09-09, for the ship artifacts f015b2fd6b4b / f015e4074694). Referencing
# them across folders would have made v5's links depend on v4 continuing to
# ship; v5 is one self-contained set.
PLACEMENT = {
    2: [("v5", "01-system-map.svg")],
    3: [("v5", "02-capsule-type-system.svg"), ("v5", "03-vault-graph.svg")],
    4: [("v5", "20-identity-width.svg")],
    5: [("v5", "04-agent-lifecycle.svg")],
    6: [("v5", "16-crew-topology.svg")],
    7: [("v5", "05-memory-architecture.svg")],
    8: [("v5", "14-event-ledger-v2.svg")],
    11: [("v5", "12-two-pipeline-dag.svg")],
    14: [("v5", "17-genesis-arrival.svg")],
    15: [("v5", "09-federation-sovereignty.svg")],
    16: [("v5", "18-release-path.svg")],
    17: [("v5", "08-enforcement-verification.svg")],
    19: [("v5", "15-gardener-loop.svg")],
    21: [("v5", "19-defect-families.svg")],
}

CAPTIONS = {
    "01-system-map.svg": "The nine ruled subsystems in three layers, with the CI lane outside the studio boundary.",
    "20-identity-width.svg": "The uid width migration, and the surfaces still carrying an 8-hex assumption.",
    "04-agent-lifecycle.svg": "Born, session, retire — and compact-continue looping back into the same generation.",
    "16-crew-topology.svg": "One agent, one clone; origin/main is the only place the copies meet.",
    "05-memory-architecture.svg": "Three scopes, and the bounded surface with no overflow destination.",
    "12-two-pipeline-dag.svg": "The dev and release pipelines; the promotion lane is dashed because it does not exist.",
    "17-genesis-arrival.svg": "Identity minted in the box (v1.94, held) against minted on the customer's machine (v1.95).",
    "18-release-path.svg": "The authorization stack end to end, with the live defects marked where they sit.",
    "08-enforcement-verification.svg": "One guard registry, two run points, and what a gate may assert.",
    "19-defect-families.svg": "The seven defect families, their measured counts, and their dispositions.",
    "02-capsule-type-system.svg": "The capsule type system (carried unchanged from v4).",
    "03-vault-graph.svg": "The vault as a graph (carried from v4).",
    "14-event-ledger-v2.svg": "The event ledger (carried from v4).",
    "09-federation-sovereignty.svg": "Federation and the sovereignty covenant (carried from v4).",
    "15-gardener-loop.svg": "The Gardener's proposal-only loop (carried from v4).",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repo_root(start: Path) -> Path:
    cur = start.resolve()
    for c in [cur, *cur.parents]:
        if (c / ".tropo").is_dir() and (c / "vault").is_dir():
            return c
    return cur


def git_head(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm_raw, body = text[3:end], text[end + 4:]
    fm = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line.strip())
        if m:
            fm[m.group(1)] = m.group(2).strip().strip("'\"")
    return fm, body


# ------------------------------------------------------------ markdown

def inline(text: str) -> str:
    """Inline markdown -> HTML. Code spans are protected first so their
    contents are never interpreted as emphasis or links."""
    spans: list[str] = []

    def stash(m):
        spans.append(html.escape(m.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)
    return text


def render_markdown(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Returns (html, toc) where toc is [(level, anchor, title)]."""
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    lines = body.splitlines()
    i = 0
    in_table = False
    seen: dict[str, int] = {}

    def anchor(title: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "section"
        seen[base] = seen.get(base, 0) + 1
        return base if seen[base] == 1 else f"{base}-{seen[base]}"

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            close_table()
            i += 1
            continue

        if stripped.startswith("```"):
            close_table()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue

        m = re.match(r"^(#{2,4})\s+(.*)$", stripped)
        if m:
            close_table()
            level = len(m.group(1))
            title = m.group(2).strip()
            a = anchor(title)
            toc.append((level, a, title))
            out.append(f'<h{level} id="{a}">{inline(title)}</h{level}>')
            i += 1
            continue

        if stripped == "---":
            close_table()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            close_table()
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            out.append('<div class="tablewrap"><table><thead><tr>'
                       + "".join(f"<th>{inline(h)}</th>" for h in headers)
                       + "</tr></thead><tbody>")
            in_table = True
            i += 2
            continue

        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            i += 1
            continue
        close_table()

        # Lists. A list item may wrap over several source lines: any following
        # line that is not blank and does not itself begin a block belongs to
        # the item above it. Getting this wrong splits a bullet mid-sentence and
        # leaves its ** markers unrendered -- which is exactly what the first
        # cut of this renderer did to the failure record.
        def collect_items(marker: str) -> list[str]:
            nonlocal i
            items: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if re.match(marker, s):
                    items.append(re.sub(marker, "", s))
                    i += 1
                    while i < len(lines):
                        nxt = lines[i].strip()
                        if not nxt or re.match(r"^(#{2,4}\s|[-*]\s|\d+\.\s|>|\||```|---$)", nxt):
                            break
                        items[-1] += " " + nxt
                        i += 1
                    continue
                break
            return [inline(x) for x in items]

        if re.match(r"^[-*]\s+", stripped):
            items = collect_items(r"^[-*]\s+")
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            items = collect_items(r"^\d+\.\s+")
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue

        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>")
            continue

        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{2,4}\s|[-*]\s|\d+\.\s|>|\||```|---$)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")

    close_table()
    return "\n".join(out), toc


def inline_svgs(html_body: str, root: Path) -> tuple[str, list[str]]:
    """Insert each placed diagram directly after its section heading."""
    used: list[str] = []
    for num, entries in sorted(PLACEMENT.items()):
        pat = re.compile(rf'(<h2 id="[^"]*">{num}\.\s.*?</h2>)', re.S)
        m = pat.search(html_body)
        if not m:
            continue
        figs = []
        for where, name in entries:
            path = root / (SVG_DIR if where == "v5" else V4_SVG_DIR) / name
            if not path.is_file():
                continue
            svg = path.read_text(encoding="utf-8")
            svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
            svg = re.sub(r"<svg ", '<svg class="diagram" ', svg, count=1)
            cap = CAPTIONS.get(name, "")
            figs.append(f'<figure>{svg}<figcaption>{html.escape(cap)}</figcaption></figure>')
            used.append(f"{where}/{name}")
        if figs:
            html_body = html_body[:m.end()] + "\n" + "\n".join(figs) + html_body[m.end():]
    return html_body, used


CSS = """
:root{--paper:#fff;--ink:#1a2332;--body:#2c3742;--muted:#5a6a7a;--line:#c5d0da;
--soft:#eef2f6;--navy:#2c4a6e;--steel:#3a6b8a;--amber:#b08a4a;--green:#4a8a6b;--red:#9c2b2b}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--body);
font:16px/1.68 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
.layout{display:flex;align-items:flex-start;max-width:1500px;margin:0 auto}
nav{position:sticky;top:0;flex:0 0 292px;max-height:100vh;overflow-y:auto;
padding:34px 20px 60px 30px;border-right:1px solid var(--line);font-size:13.5px}
nav .navhead{font-weight:700;color:var(--ink);font-size:12px;letter-spacing:.1em;
text-transform:uppercase;margin:0 0 12px}
nav a{display:block;color:var(--muted);text-decoration:none;padding:3px 0;line-height:1.4}
nav a:hover{color:var(--navy)}
nav a.l3{padding-left:14px;font-size:12.5px}
main{flex:1 1 auto;min-width:0;padding:44px 52px 120px;max-width:1000px}
h1{font-size:34px;line-height:1.2;color:var(--ink);margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:23px;color:var(--ink);margin:52px 0 14px;padding-top:20px;
border-top:2px solid var(--navy);letter-spacing:-.01em}
h3{font-size:17px;color:var(--navy);margin:30px 0 8px}
h4{font-size:15px;color:var(--ink);margin:22px 0 6px}
p{margin:0 0 14px;max-width:76ch}
ul,ol{max-width:76ch;margin:0 0 14px;padding-left:22px}
li{margin:0 0 6px}
a{color:var(--steel)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.875em;
background:var(--soft);padding:1px 5px;border-radius:3px;color:var(--ink)}
pre{background:var(--soft);border:1px solid var(--line);border-radius:6px;
padding:14px 16px;overflow-x:auto;max-width:76ch}
pre code{background:none;padding:0;font-size:13px;line-height:1.5}
blockquote{margin:0 0 16px;padding:12px 18px;border-left:4px solid var(--navy);
background:var(--soft);max-width:76ch}
blockquote p{margin:0}
.tablewrap{overflow-x:auto;margin:0 0 18px;border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:var(--soft);color:var(--ink);font-size:12px;letter-spacing:.05em;
text-transform:uppercase;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
hr{border:none;border-top:1px solid var(--line);margin:26px 0}
figure{margin:22px 0 26px;max-width:100%}
svg.diagram{width:100%;height:auto;display:block;border:1px solid var(--line);
border-radius:6px;background:#fff}
figcaption{color:var(--muted);font-size:13px;margin-top:8px;font-style:italic}
.docmeta{background:var(--soft);border:1px solid var(--line);border-left:4px solid var(--navy);
border-radius:6px;padding:16px 20px;margin:0 0 30px;font-size:14px}
.docmeta b{color:var(--ink)}
.kicker{color:var(--muted);font-size:13px;letter-spacing:.12em;text-transform:uppercase;
font-weight:700;margin:0 0 10px}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);
color:var(--muted);font-size:13px}
@media(max-width:1080px){.layout{display:block}nav{position:static;max-height:none;
border-right:none;border-bottom:1px solid var(--line);flex:none;padding:24px 30px}
main{padding:30px 30px 90px}}
@media print{nav{display:none}main{max-width:none;padding:0}h2{page-break-after:avoid}
figure{page-break-inside:avoid}}
"""


def build(root: Path) -> tuple[str, dict, dict]:
    src = root / SRC
    raw = src.read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)
    body_html, toc = render_markdown(body)
    body_html, used = inline_svgs(body_html, root)

    title = fm.get("title", "Tropo L1 Architecture Review v5")
    commit = fm.get("measured_at_commit", "unknown")
    on = fm.get("measured_on", "")
    ver = fm.get("system_version", "")

    nav = ['<nav><p class="navhead">Contents</p>']
    for level, a, t in toc:
        if level > 3:
            continue
        cls = "" if level == 2 else ' class="l3"'
        nav.append(f'<a href="#{a}"{cls}>{html.escape(t)}</a>')
    nav.append("</nav>")

    head = (
        f'<p class="kicker">Tropo · Architecture Review</p>'
        f"<h1>{html.escape(title)}</h1>"
        f'<div class="docmeta">'
        f"<b>Measured</b> against the tree at commit <code>{html.escape(commit)}</code>"
        f"{' on ' + html.escape(on) if on else ''}"
        f"{', studio v' + html.escape(ver) if ver else ''}. "
        f"<b>Supersedes</b> the v4 review and its four appended delta layers. "
        f"This page is a rendering; the canonical document is the markdown at "
        f"<code>{SRC}</code>, and this file is regenerated from it "
        f"(<code>tropo-render-architecture-review.py</code>, <code>--check-stale</code> gated)."
        f"</div>"
    )

    page = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{CSS}</style>\n{{STAMP}}\n</head>\n"
        f'<body>\n<div class="layout">\n{"".join(nav)}\n<main>\n{head}\n{body_html}\n'
        f"<footer>Generated from <code>{SRC}</code> by "
        f"<code>vault/tools/tropo-render-architecture-review.py</code>. "
        f"Diagrams inlined: {len(used)}.</footer>\n</main>\n</div>\n</body>\n</html>\n"
    )

    fp = {"source": sha(raw)}
    for where, name in [e for v in PLACEMENT.values() for e in v]:
        p = root / (SVG_DIR if where == "v5" else V4_SVG_DIR) / name
        fp[f"svg:{where}/{name}"] = sha(p.read_text(encoding="utf-8")) if p.is_file() else "ABSENT"
    fp["composite"] = sha(json.dumps(fp, sort_keys=True))
    return page, fp, {"sections": len([t for t in toc if t[0] == 2]), "diagrams": len(used)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render the Architecture Review to HTML.")
    ap.add_argument("--output", default=None)
    ap.add_argument("--check-stale", action="store_true")
    args = ap.parse_args(argv)

    root = repo_root(Path.cwd())
    if not (root / SRC).is_file():
        print(f"REFUSING: {SRC} not found — nothing to render.", file=sys.stderr)
        return 2

    out = Path(args.output) if args.output else root / OUT
    page, fp, stats = build(root)

    if args.check_stale:
        if not out.is_file():
            print(f"STALE: {out} has not been rendered yet.")
            return 1
        text = out.read_text(encoding="utf-8", errors="replace")
        m = re.search(re.escape(MARKER) + r"\s*(\{.*?\})\s*-->", text, re.S)
        if not m:
            print(f"STALE: {out} carries no fingerprint block.")
            return 1
        try:
            was = json.loads(m.group(1))
        except json.JSONDecodeError:
            print(f"STALE: {out}'s fingerprint block does not parse.")
            return 1
        if was.get("composite") != fp["composite"]:
            moved = [k for k, v in fp.items() if k != "composite" and was.get(k) != v]
            print(f"STALE: inputs moved: {', '.join(moved) or 'unknown'}. Re-render.")
            return 1
        print(f"FRESH: {out} matches its inputs (composite {fp['composite'][:12]}).")
        return 0

    doc = page.replace("{STAMP}", f"{MARKER} {json.dumps(fp, sort_keys=True)} -->")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"rendered {out} — {stats['sections']} sections, {stats['diagrams']} diagrams inlined, "
          f"{len(doc):,} bytes, composite {fp['composite'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
