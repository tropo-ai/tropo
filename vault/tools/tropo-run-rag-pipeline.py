#!/usr/bin/env python3
"""
---
uid: 91c8c388
name: run-rag-pipeline
description: Execute the tropo-app MoPower RAG pipeline on behalf of an agent — plan → research → draft → verify → file. Mirrors the full Tropo Power UI flow against the running dev server (localhost:3000 by default).
version: "0.1"
author: talos-t22
created: "2026-06-28"
tags:
  - tool
  - rag-pipeline
  - mopower
  - l2-bridge
  - talos-t22
---

Run the tropo-app MoPower RAG pipeline from the command line (no browser needed).

Calls the same two API routes the frontend uses:
  1. POST /api/query/plan   — route + plan (6–8 steps typical)
  2. POST /api/query/execute — execute via SSE stream → done event

Writes the artifact markdown to disk and prints a summary.

Usage examples:
  python3 .tropo/scripts/tropo.py run-rag-pipeline \\
    --query "Write a 2-page blog on agentic disruption..." \\
    --kb kb-marketing-v14.1-mo-mini \\
    --role "Executive Leadership" --quality premium

  python3 .tropo/scripts/tropo.py run-rag-pipeline \\
    --query "Prep brief for MGB meeting" --kb mos-v13.0-mo-mini \\
    --output-dir /tmp/briefs
"""
import sys, json, argparse, os
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import http.client

# ── KB discovery ─────────────────────────────────────────────────────────────
# Matches tropo-app lib/kb-bundle.ts ADR-040 scan order.

def _kb_search_roots(app_root: Path):
    return [
        app_root / "kb",
        app_root / "releases" / "kb",
        app_root.parent / "tropo-releases" / "kb",
    ]

def resolve_kb_path(kb_name: str, app_root: Path) -> str:
    """Resolve a KB bundle name to its absolute directory path."""
    if Path(kb_name).is_absolute() and Path(kb_name).is_dir():
        return kb_name
    for root in _kb_search_roots(app_root):
        candidate = root / kb_name
        if candidate.is_dir():
            return str(candidate)
    raise SystemExit(
        f"KB bundle '{kb_name}' not found.\n"
        f"Searched: {[str(r) for r in _kb_search_roots(app_root)]}\n"
        f"Available bundles:\n" + "\n".join(_list_kb_bundles(app_root))
    )

def _list_kb_bundles(app_root: Path) -> list:
    bundles = []
    for root in _kb_search_roots(app_root):
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir():
                    bundles.append(f"  {d.name}  ({d})")
    return bundles or ["  (none found)"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    """POST JSON, return parsed response dict."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} from {url}: {body[:300]}")
    except URLError as e:
        raise SystemExit(f"Cannot reach {url}: {e.reason}\n(Is the tropo-app dev server running?)")


def _stream_sse(url: str, payload: dict, timeout: int = 360, on_event=None):
    """POST to an SSE endpoint; call on_event(type, data) for each event; return done-event data."""
    data = json.dumps(payload).encode()
    parsed = None
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        conn = http.client.HTTPConnection(p.netloc, timeout=timeout)
        conn.request("POST", p.path, body=data, headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        })
        resp = conn.getresponse()
        if resp.status != 200:
            raise SystemExit(f"HTTP {resp.status} from {url}: {resp.read(512).decode(errors='replace')}")

        # Parse SSE line-by-line
        event_type = None
        buf = []
        while True:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode(errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                buf.append(line[5:].strip())
            elif line == "":
                if event_type and buf:
                    payload_str = "\n".join(buf)
                    try:
                        evt_data = json.loads(payload_str)
                    except json.JSONDecodeError:
                        evt_data = {"raw": payload_str}
                    if on_event:
                        on_event(event_type, evt_data)
                    if event_type == "done":
                        parsed = evt_data
                        break
                    if event_type == "error":
                        raise SystemExit(f"Pipeline error: {evt_data.get('message', payload_str)}")
                event_type = None
                buf = []
    except (ConnectionRefusedError, OSError) as e:
        raise SystemExit(f"Cannot reach {url}: {e}\n(Is the tropo-app dev server running?)")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return parsed


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Execute the tropo-app MoPower RAG pipeline — plan → research → draft → verify → file."
    )
    ap.add_argument("--query", required=True, help="The research/brief request (free text)")
    ap.add_argument("--kb", required=True,
                    help="KB bundle name (e.g. kb-marketing-v14.1-mo-mini) or absolute path")
    ap.add_argument("--role", default="Executive Leadership",
                    help="Config: role context (default: 'Executive Leadership')")
    ap.add_argument("--quality", default="premium", choices=["standard", "premium"],
                    help="Config: output quality (default: premium → Opus)")
    ap.add_argument("--output-dir", default=".",
                    help="Directory to write the output .md file (default: cwd)")
    ap.add_argument("--output", default=None,
                    help="Override output filename (default: use filename from pipeline)")
    ap.add_argument("--host", default="http://localhost:3000",
                    help="tropo-app base URL (default: http://localhost:3000)")
    ap.add_argument("--app-root", default=None,
                    help="Path to tropo-app root (default: auto-detect sibling of argo-os)")
    ap.add_argument("--verbose", action="store_true", help="Print step events as they arrive")
    args = ap.parse_args(argv)

    # Resolve app root
    if args.app_root:
        app_root = Path(args.app_root).resolve()
    else:
        # Auto-detect: try studio-sibling first, then one level up (tropo-app lives at
        # /Users/mike/dev/tropo-app, not inside tropo-studios/).
        studio_root = Path(__file__).parent.parent.parent  # vault/tools -> vault -> studio
        candidates = [
            studio_root.parent / "tropo-app",         # sibling of studio root
            studio_root.parent.parent / "tropo-app",  # one level up (argo-os inside tropo-studios)
        ]
        app_root = next((c for c in candidates if c.is_dir()), None)
        if not app_root:
            raise SystemExit(
                f"Could not auto-detect tropo-app. Tried: {[str(c) for c in candidates]}\n"
                f"Pass --app-root <path> explicitly."
            )

    kb_path = resolve_kb_path(args.kb, app_root)
    config = {"role": args.role, "quality": args.quality}
    host = args.host.rstrip("/")

    print(f"[run-rag-pipeline] Query: {args.query[:80]}{'…' if len(args.query) > 80 else ''}")
    print(f"[run-rag-pipeline] KB: {kb_path}")
    print(f"[run-rag-pipeline] Config: {config}")
    print(f"[run-rag-pipeline] Host: {host}")

    # ── Step 1: Plan ─────────────────────────────────────────────────────────
    print("\n[run-rag-pipeline] Step 1/2 — planning...")
    plan_resp = _post_json(
        f"{host}/api/query/plan",
        {"query": args.query, "kb_path": kb_path, "config": config},
        timeout=45,
    )

    if plan_resp.get("bypass"):
        raise SystemExit("[run-rag-pipeline] Planner returned bypass=true — query may be a simple chat, not a RAG brief. Try a more specific document-generation prompt.")

    plan = plan_resp.get("plan")
    context = plan_resp.get("context", {})
    if not plan or not plan.get("steps"):
        raise SystemExit(f"[run-rag-pipeline] Planner returned no steps: {json.dumps(plan_resp)[:300]}")

    steps = plan["steps"]
    print(f"[run-rag-pipeline] Plan: {len(steps)} steps — {plan.get('strategy', '')[:60]}")
    for s in steps:
        print(f"  {s['id']} ({s['type']}): {s.get('description', '')[:70]}")

    # ── Step 2: Execute ───────────────────────────────────────────────────────
    print(f"\n[run-rag-pipeline] Step 2/2 — executing (this takes 2–5 minutes)...")

    def on_event(evt_type, evt_data):
        if evt_type == "step_start":
            desc = evt_data.get("description", "")[:60]
            print(f"  → {evt_data.get('stepId', '?')} starting: {desc}")
        elif evt_type == "step_complete":
            print(f"  ✓ {evt_data.get('stepId', '?')} done — {evt_data.get('summary', '')[:60]}")
        elif args.verbose:
            print(f"  [{evt_type}] {str(evt_data)[:100]}")

    done = _stream_sse(
        f"{host}/api/query/execute",
        {
            "query": args.query,
            "plan": plan,
            "config": config,
            "routerContext": context,
        },
        timeout=360,
        on_event=on_event if (args.verbose or True) else None,
    )

    if not done:
        raise SystemExit("[run-rag-pipeline] Stream ended without a 'done' event.")

    artifact_md = done.get("artifact_markdown", "")
    artifact_fn = done.get("artifact_filename") or "rag-pipeline-output.md"
    chat_answer = done.get("chat_answer", "")

    if not artifact_md:
        raise SystemExit(f"[run-rag-pipeline] Done event had no artifact_markdown. chat_answer: {chat_answer[:200]}")

    # ── Write output ──────────────────────────────────────────────────────────
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (args.output or artifact_fn)
    out_file.write_text(artifact_md, encoding="utf-8")

    print(f"\n[run-rag-pipeline] Done.")
    print(f"  chat_answer: {chat_answer[:120]}")
    print(f"  output:      {out_file}  ({len(artifact_md)} chars)")

    assessment = done.get("assessment") or []
    if assessment:
        met = sum(1 for a in assessment if a.get("met"))
        print(f"  assessment:  {met}/{len(assessment)} plan items met")

    sources = done.get("sources") or []
    web = [s for s in sources if s.get("url")]
    kb_s = [s for s in sources if not s.get("url")]
    print(f"  sources:     {len(web)} web  +  {len(kb_s)} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
