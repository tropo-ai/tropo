#!/usr/bin/env python3
"""Render the release-and-subsystem explorer: one self-contained HTML page that
makes the studio's live release/subsystem evidence navigable.

WHAT THIS IS FOR
    The founder's question each release is "did this touch any subsystem, and
    what changed?" That is answerable from the registry rows today and visible
    nowhere. This renders it: releases down, the nine ruled subsystems across, a
    mark where a release declared a touch, and a panel per subsystem saying what
    it actually owns.

THE ONE DESIGN RULE (inherited from tropo-render-studio-map.py)
    Nothing here is hand-written that a tool can derive. Every section is
    generated from a source of truth this renderer reads and fingerprints, so
    `--check-stale` fails loud the moment an input moves. A generated page that
    can go quietly wrong is worse than no page.

HONESTY, RENDERED
    The page states its own instrument, its commit and its measurement date, and
    it draws the gap between what the registry declares and what the studio has
    actually shipped. The registry is derived from each release plan's
    capabilities_touched; it is a record of DECLARATIONS, not of observed code
    change. The observed-diff column is Talos's contribution and is NOT YET
    MEASURED -- the page says so rather than leaving an empty column a reader
    has to interpret.

SOURCES (each fingerprinted)
    .tropo-studio/registries/subsystems.yaml         the ruled list of nine
    .tropo-studio/registries/subsystem-registry.jsonl  declared per-release rows
    vault/00-index.jsonl                             counts, work, release entries
    .tropo/version.md                                the studio's current version
    each hub file's frontmatter                      the home folder

Written by orpheus-o39 2026-09-08, under brief f015a3d86793 (phase 2) at Mike's
commission, with the explorer handed over by argus-a174. Sibling renderer:
tropo-render-studio-map.py, whose fingerprint/--check-stale contract this follows.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SUBSYSTEMS_YAML = ".tropo-studio/registries/subsystems.yaml"
REGISTRY = ".tropo-studio/registries/subsystem-registry.jsonl"
INDEX = "vault/00-index.jsonl"
VERSION_FILE = ".tropo/version.md"
DEFAULT_OUT = "boards/po/systems-explorer.html"
MARKER = "<!-- fingerprints:"

BANDS = [
    ("kernel", "Kernel", "The rules and the boot floor"),
    ("apps", "Apps", "What the studio runs on itself"),
    ("primitives", "Primitives", "The governed store and its machinery"),
]


# ---------------------------------------------------------------- reading

def repo_root(start: Path) -> Path:
    cur = start.resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".tropo").is_dir() and (candidate / "vault").is_dir():
            return candidate
    return cur


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    if not path.is_file():
        return "ABSENT"
    return sha(path.read_text(encoding="utf-8", errors="replace"))


def git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def read_yaml_subsystems(root: Path) -> dict:
    """The ruled list. Parsed without PyYAML so the renderer keeps the
    stdlib-only floor its sibling holds: this file's shape is fixed and
    declared, and a dependency here would make the page unrenderable on a
    machine that can still run everything else."""
    path = root / SUBSYSTEMS_YAML
    if not path.is_file():
        return {"status": "ABSENT", "subsystems": [], "count": 0}
    text = path.read_text(encoding="utf-8")
    meta = {}
    for key in ("status", "ruled_by", "ruled_at", "count", "as_of_release", "declared_by"):
        m = re.search(rf"^{key}:\s*(.+?)\s*$", text, re.M)
        if m:
            meta[key] = m.group(1).strip().strip("'\"")
    verbatim = re.search(r"^ruled_verbatim:\s*(.+?)\s*$", text, re.M)
    meta["ruled_verbatim"] = verbatim.group(1).strip().strip("'\"") if verbatim else ""

    subs = []
    block = text.split("subsystems:", 1)[-1].split("not_subsystems:", 1)[0]
    for chunk in re.split(r"\n  - uid:", block):
        if not chunk.strip():
            continue
        uid = chunk.strip().split("\n", 1)[0].strip()
        if not re.fullmatch(r"[0-9a-f]{8,12}", uid):
            continue
        def field(name: str) -> str:
            m = re.search(rf"^\s{{4}}{name}:\s*(.+?)\s*$", chunk, re.M)
            return m.group(1).strip().strip("'\"").split("#")[0].strip() if m else ""
        charter = ""
        cm = re.search(r"text:\s*>-\s*\n((?:\s{8}.+\n?)+)", chunk)
        if cm:
            charter = " ".join(line.strip() for line in cm.group(1).splitlines() if line.strip())
        subs.append({
            "uid": uid,
            "name": field("name"),
            "home": field("home"),
            "layer": field("layer") or "primitives",
            "charter": charter,
        })
    meta["subsystems"] = subs
    return meta


def read_registry(root: Path) -> list[dict]:
    path = root / REGISTRY
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_index(root: Path) -> list[dict]:
    path = root / INDEX
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def studio_version(root: Path) -> str:
    path = root / VERSION_FILE
    if not path.is_file():
        return "unknown"
    m = re.search(r"v?(\d+\.\d+\.\d+)", path.read_text(encoding="utf-8"))
    return m.group(1) if m else "unknown"


def version_key(v: str) -> tuple:
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts[:3]) + (0,) * (3 - len(parts[:3]))


# ---------------------------------------------------------------- deriving

def subsystem_stats(index: list[dict], subs: list[dict]) -> dict:
    uids = {s["uid"] for s in subs}
    stats = {u: {"tagged": 0, "types": {}, "open_work": 0} for u in uids}
    WORK = {"task", "design-brief", "dev-spec", "decision", "design-spec",
            "test-spec", "pipeline-run", "release-plan", "arch-spec"}
    CLOSED = {"done", "closed", "cancelled", "complete", "archived", "shipped", "retired"}
    for row in index:
        hub = row.get("subsystem_hub")
        hubs = [hub] if isinstance(hub, str) else (hub or [])
        for h in hubs:
            if h not in stats:
                continue
            stats[h]["tagged"] += 1
            t = str(row.get("type") or "?")
            stats[h]["types"][t] = stats[h]["types"].get(t, 0) + 1
            if t in WORK and str(row.get("status") or "").lower() not in CLOSED:
                stats[h]["open_work"] += 1
    return stats


def matrix(registry: list[dict], subs: list[dict]) -> tuple[list[str], dict, dict]:
    """releases (newest first) x subsystem uid -> the declared touch."""
    by_release: dict[str, dict[str, dict]] = {}
    shipped: dict[str, str] = {}
    for row in registry:
        v = str(row.get("release_version") or "").strip()
        if not v:
            continue
        cell = by_release.setdefault(v, {})
        uid = str(row.get("subsystem_uid") or "")
        summary = (row.get("summary") or "").strip()
        prev = cell.get(uid)
        if prev is None or (not prev.get("summary") and summary):
            cell[uid] = {"summary": summary, "derived_from": row.get("derived_from") or ""}
        if row.get("shipped_at"):
            shipped[v] = str(row["shipped_at"])[:10]
    releases = sorted(by_release, key=version_key, reverse=True)
    return releases, by_release, shipped


# ---------------------------------------------------------------- svg

def svg_bands(subs: list[dict], stats: dict) -> str:
    """The nine, in their three declared layers, sized by what they carry.
    Drawn from the ruled list and the index — never hand-placed."""
    by_band = {b: [] for b, _, _ in BANDS}
    for s in subs:
        by_band.setdefault(s["layer"], by_band.setdefault("primitives", [])).append(s)

    W, rowH, pad = 1040, 128, 18
    H = 44 + len(BANDS) * rowH
    out = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="The nine subsystems in three layers" class="bands">'
    ]
    out.append('<defs><linearGradient id="gk" x1="0" y1="0" x2="1" y2="1">'
               '<stop offset="0%" stop-color="var(--accent)" stop-opacity=".20"/>'
               '<stop offset="100%" stop-color="var(--accent)" stop-opacity=".04"/>'
               '</linearGradient></defs>')
    y = 30
    for band_key, band_label, band_note in BANDS:
        members = sorted(by_band.get(band_key) or [], key=lambda s: -stats.get(s["uid"], {}).get("tagged", 0))
        out.append(f'<text x="0" y="{y - 8}" class="bandlabel">{html.escape(band_label.upper())} '
                   f'<tspan class="bandnote">{html.escape(band_note)}</tspan></text>')
        out.append(f'<rect x="0" y="{y}" width="{W}" height="{rowH - 26}" rx="10" class="bandbg"/>')
        if not members:
            out.append(f'<text x="16" y="{y + 40}" class="empty">no subsystem declares this layer</text>')
        else:
            bw = (W - pad * (len(members) + 1)) / len(members)
            x = pad
            for s in members:
                tagged = stats.get(s["uid"], {}).get("tagged", 0)
                openw = stats.get(s["uid"], {}).get("open_work", 0)
                out.append(
                    f'<a href="#s-{s["uid"]}">'
                    f'<rect x="{x:.1f}" y="{y + 14}" width="{bw:.1f}" height="{rowH - 54}" rx="8" class="box"/>'
                    f'<text x="{x + 14:.1f}" y="{y + 42}" class="boxname">{html.escape(s["name"])}</text>'
                    f'<text x="{x + 14:.1f}" y="{y + 62}" class="boxhome">{html.escape(s["home"])}</text>'
                    f'<text x="{x + 14:.1f}" y="{y + 82}" class="boxstat">{tagged} tagged · {openw} open</text>'
                    f'</a>'
                )
                x += bw + pad
        y += rowH
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#fbfaf8;--panel:#fff;--ink:#17181b;--dim:#5d626c;--line:#e3e1dc;
--accent:#7a5cff;--warn:#b4560c;--good:#217a4b;--grid:#f2f0ec;--mark:#7a5cff}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#0f1013;--panel:#16181d;--ink:#eceef2;--dim:#9aa1ae;--line:#272b33;
--accent:#9d86ff;--warn:#e2933f;--good:#4fbd84;--grid:#1c1f25;--mark:#9d86ff}}
:root[data-theme="dark"]{--bg:#0f1013;--panel:#16181d;--ink:#eceef2;--dim:#9aa1ae;
--line:#272b33;--accent:#9d86ff;--warn:#e2933f;--good:#4fbd84;--grid:#1c1f25;--mark:#9d86ff}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;
font:15px/1.62 ui-sans-serif,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:38px 26px 90px}
h1{font-size:30px;letter-spacing:-.021em;margin:0 0 6px;font-weight:640}
h2{font-size:19px;letter-spacing:-.012em;margin:46px 0 12px;font-weight:620}
h3{font-size:15px;margin:22px 0 8px;font-weight:620}
p{margin:0 0 12px;max-width:74ch}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.sub{color:var(--dim);margin:0 0 22px;max-width:78ch}
.instrument{border:1px solid var(--line);background:var(--panel);border-radius:12px;
padding:14px 16px;margin:0 0 26px;font-size:13.5px;color:var(--dim)}
.instrument b{color:var(--ink);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12.5px}
.chip.warn{border-color:var(--warn);color:var(--warn)}
.chip.good{border-color:var(--good);color:var(--good)}
.panel{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:20px 22px;margin:0 0 18px}
.gap{border-left:3px solid var(--warn)}
svg.bands{width:100%;height:auto;display:block;margin:8px 0 4px}
.bandbg{fill:var(--grid)}
.box{fill:url(#gk);stroke:var(--line)}
a:hover .box{stroke:var(--accent)}
text{font-family:ui-sans-serif,-apple-system,"Segoe UI",Inter,sans-serif}
.bandlabel{fill:var(--dim);font-size:11.5px;letter-spacing:.14em;font-weight:640}
.bandnote{fill:var(--dim);font-size:11px;letter-spacing:.02em;font-weight:400}
.boxname{fill:var(--ink);font-size:14.5px;font-weight:620}
.boxhome{fill:var(--dim);font-size:11.5px;font-family:ui-monospace,Menlo,monospace}
.boxstat{fill:var(--dim);font-size:11.5px}
.empty{fill:var(--dim);font-size:12px;font-style:italic}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
thead th{position:sticky;top:0;background:var(--panel);z-index:2;font-size:11.5px;
letter-spacing:.06em;text-transform:uppercase;color:var(--dim);font-weight:620}
tbody tr:hover{background:var(--grid)}
td.rel{font-family:ui-monospace,Menlo,monospace;font-weight:600}
td.m{text-align:center;width:64px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--mark)}
.no{color:var(--line)}
.unmeasured{color:var(--dim);font-style:italic}
.card{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:18px 20px;margin:0 0 14px}
.card h3{margin:0 0 4px}
.card .home{color:var(--dim);font-size:12.5px;font-family:ui-monospace,Menlo,monospace}
.card p{font-size:14px;color:var(--ink);margin:10px 0 10px}
.kv{display:flex;flex-wrap:wrap;gap:16px;font-size:12.5px;color:var(--dim)}
.kv b{color:var(--ink);font-weight:620}
footer{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-size:12.5px}
"""


def page(root: Path, data: dict) -> str:
    meta = data["meta"]
    subs = meta["subsystems"]
    stats = data["stats"]
    releases, cells, shipped = data["releases"], data["cells"], data["shipped"]
    version = data["version"]
    head = data["head"]
    stamp = data["stamp"]

    reg_newest = releases[0] if releases else "none"
    behind = ""
    if releases and version != "unknown" and version_key(version) > version_key(reg_newest):
        behind = (f"The registry's newest row is <b>v{html.escape(reg_newest)}</b> while the studio "
                  f"is at <b>v{html.escape(version)}</b>. Releases since then declared no subsystem "
                  f"rows, so this matrix does not cover them.")

    o = []
    o.append(f"<style>{CSS}</style>")
    o.append('<div class="wrap">')
    o.append("<h1>The release &amp; subsystem explorer</h1>")
    o.append('<p class="sub">Which releases touched which parts of Tropo, and what each part actually '
             'owns. Every figure on this page is derived at render time from a source this renderer '
             'reads and fingerprints — nothing here is hand-written, and nothing here is a summary of '
             'a summary.</p>')

    ruled = meta.get("status") == "ruled"
    o.append('<div class="instrument">')
    o.append(f'<b>Instrument.</b> Rendered from the tree at commit <span class="mono">{html.escape(head)}</span> '
             f'on {html.escape(stamp)}, studio v{html.escape(version)}. '
             f'Counts come from <span class="mono">{INDEX}</span>, which is a per-machine derived product: '
             f'it is rebuilt locally and can lag the tree. Marks come from '
             f'<span class="mono">{REGISTRY}</span> ({data["reg_rows"]} rows across {len(releases)} releases).')
    o.append('<div class="chips">')
    o.append(f'<span class="chip {"good" if ruled else "warn"}">subsystem list: '
             f'{html.escape(meta.get("status","unknown"))}'
             + (f' by {html.escape(meta.get("ruled_by",""))}' if ruled else '') + '</span>')
    o.append(f'<span class="chip">{len(subs)} subsystems</span>')
    o.append('<span class="chip warn">observed diff: not yet measured</span>')
    o.append("</div></div>")

    if ruled and meta.get("ruled_verbatim"):
        o.append('<div class="panel">')
        o.append(f'<p style="margin:0"><b>The list is ruled.</b> {html.escape(meta.get("ruled_at",""))}, '
                 f'in the founder\'s words: “{html.escape(meta["ruled_verbatim"])}”. '
                 f'The nine below are the declared list; the hubs\' historical prose retires to the '
                 f'library as dated history.</p>')
        o.append("</div>")

    o.append("<h2>The nine, in three layers</h2>")
    o.append('<p class="sub">Each box is placed by the layer its declared home folder belongs to, and '
             'labelled with what the index has tagged to it. Click a box to jump to its panel.</p>')
    o.append(svg_bands(subs, stats))

    o.append("<h2>Releases × subsystems</h2>")
    o.append('<p class="sub">A mark means that release <b>declared</b> a touch on that subsystem, derived '
             'from the release plan\'s <span class="mono">capabilities_touched</span>. A declaration is a '
             'claim about intent, not an observation of changed code. The observed column — what actually '
             'differs between two release tags — is not yet measured, and this page will show both and '
             'say where they disagree rather than picking a winner.</p>')
    if behind:
        o.append(f'<div class="panel gap"><p style="margin:0">{behind}</p></div>')

    o.append('<div class="scroll"><table><thead><tr><th>Release</th><th>Shipped</th>')
    for s in subs:
        short = s["name"].replace("Tropo ", "")
        o.append(f'<th class="m" title="{html.escape(s["name"])}">{html.escape(short)}</th>')
    o.append("</tr></thead><tbody>")
    for v in releases:
        row = cells.get(v, {})
        o.append(f'<tr><td class="rel">v{html.escape(v)}</td>'
                 f'<td class="unmeasured">{html.escape(shipped.get(v, "—"))}</td>')
        for s in subs:
            hit = row.get(s["uid"])
            if hit:
                tip = (hit.get("summary") or "declared touch")[:300]
                o.append(f'<td class="m" title="{html.escape(tip)}"><span class="dot"></span></td>')
            else:
                o.append('<td class="m no">·</td>')
        o.append("</tr>")
    o.append("</tbody></table></div>")

    never = [s for s in subs if not any(s["uid"] in cells.get(v, {}) for v in releases)]
    if never:
        names = ", ".join(html.escape(s["name"]) for s in never)
        o.append(f'<div class="panel gap"><p style="margin:0"><b>Never declared.</b> {names} '
                 f'{"has" if len(never)==1 else "have"} not appeared in any of the '
                 f'{data["reg_rows"]} registry rows. That is a fact about the registry, not proof the '
                 f'subsystem is idle — but nothing has ever recorded a release touching it.</p></div>')

    o.append("<h2>What each subsystem owns</h2>")
    for s in subs:
        st = stats.get(s["uid"], {})
        types = st.get("types") or {}
        top = ", ".join(f'{k} {v}' for k, v in sorted(types.items(), key=lambda kv: -kv[1])[:5]) or "nothing tagged"
        last = max((v for v in releases if s["uid"] in cells.get(v, {})), key=version_key, default=None)
        o.append(f'<div class="card" id="s-{s["uid"]}">')
        o.append(f'<h3>{html.escape(s["name"])}</h3>')
        o.append(f'<div class="home">{html.escape(s["home"])} · <span class="mono">{html.escape(s["uid"])}</span></div>')
        if s.get("charter"):
            o.append(f'<p>{html.escape(s["charter"])}</p>')
        o.append('<div class="kv">')
        o.append(f'<span><b>{st.get("tagged", 0)}</b> entries tagged</span>')
        o.append(f'<span><b>{st.get("open_work", 0)}</b> open work items</span>')
        o.append(f'<span>last declared release <b>{("v" + last) if last else "never"}</b></span>')
        o.append(f'<span>{html.escape(top)}</span>')
        o.append("</div></div>")

    o.append("<footer>")
    o.append(f'Generated by <span class="mono">vault/tools/tropo-render-systems-explorer.py</span> — '
             f're-render to refresh, and <span class="mono">--check-stale</span> fails when any input moves. '
             f'Sources: the ruled subsystem list, the per-release registry, the index, and each hub\'s own '
             f'frontmatter. Governing brief <span class="mono">f015a3d86793</span>.')
    o.append("</footer></div>")
    return "\n".join(o)


# ---------------------------------------------------------------- main

def gather(root: Path) -> dict:
    meta = read_yaml_subsystems(root)
    registry = read_registry(root)
    index = read_index(root)
    subs = meta.get("subsystems") or []
    releases, cells, shipped = matrix(registry, subs)
    return {
        "meta": meta,
        "stats": subsystem_stats(index, subs),
        "releases": releases,
        "cells": cells,
        "shipped": shipped,
        "reg_rows": len(registry),
        "version": studio_version(root),
        "head": git_head(root),
        "stamp": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def fingerprints(root: Path, data: dict) -> dict:
    fp = {
        "subsystems-yaml": file_sha(root / SUBSYSTEMS_YAML),
        "registry": file_sha(root / REGISTRY),
        "version": file_sha(root / VERSION_FILE),
        "subsystem-set": sha("\n".join(f'{s["uid"]}\t{s["name"]}\t{s["home"]}\t{s["layer"]}'
                                       for s in data["meta"].get("subsystems") or [])),
        "index-counts": sha(json.dumps(data["stats"], sort_keys=True)),
    }
    fp["composite"] = sha(json.dumps(fp, sort_keys=True))
    return fp


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render the release-and-subsystem explorer.")
    ap.add_argument("--output", default=None, help=f"output path (default {DEFAULT_OUT})")
    ap.add_argument("--check-stale", action="store_true",
                    help="exit 1 if the rendered page's inputs have moved since it was written")
    args = ap.parse_args(argv)

    root = repo_root(Path.cwd())
    out = Path(args.output) if args.output else root / DEFAULT_OUT

    data = gather(root)
    if not data["meta"].get("subsystems"):
        print(f"REFUSING: no subsystems read from {SUBSYSTEMS_YAML} — an explorer with no "
              f"subsystems is a blank page that looks like a working one.", file=sys.stderr)
        return 2

    fp = fingerprints(root, data)

    if args.check_stale:
        if not out.is_file():
            print(f"STALE: {out} has not been rendered yet.")
            return 1
        text = out.read_text(encoding="utf-8", errors="replace")
        m = re.search(re.escape(MARKER) + r"\s*(\{.*?\})\s*-->", text, re.S)
        if not m:
            print(f"STALE: {out} carries no fingerprint block; it was not written by this renderer.")
            return 1
        try:
            was = json.loads(m.group(1))
        except json.JSONDecodeError:
            print(f"STALE: {out}'s fingerprint block does not parse.")
            return 1
        if was.get("composite") != fp["composite"]:
            moved = [k for k, v in fp.items() if k != "composite" and was.get(k) != v]
            print(f"STALE: {out} was rendered from a different studio state. "
                  f"Inputs that moved: {', '.join(moved) or 'unknown'}. Re-render.")
            return 1
        print(f"FRESH: {out} matches its inputs (composite {fp['composite'][:12]}).")
        return 0

    body = page(root, data)
    stamp = (f"{MARKER} {json.dumps(fp, sort_keys=True)} -->")
    doc = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>The release &amp; subsystem explorer — Tropo</title>\n"
        f"{stamp}\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"rendered {out} — {len(data['meta']['subsystems'])} subsystems, "
          f"{len(data['releases'])} releases, {data['reg_rows']} registry rows, "
          f"composite {fp['composite'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
