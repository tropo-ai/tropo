#!/usr/bin/env python3
"""tropo — the L1 tool-discovery dispatcher (serverless, MCP-shaped).

Makes `vault/tools/` a FINDABLE surface — the way a well-laid-out studio,
workshop, or dojo is findable: you can see what's on the wall, and reach for
any of it by name.

The v1.61 tools-in-vault migration made every tool single-file-truth at
`vault/tools/<uid>.<ext>` — a governance win, but UID-addressing lost
name-based discovery (an agent told to run `query-events` cannot find
`1545ac97.py`). This dispatcher restores the name layer over the one source of
truth (the tool files' own frontmatter), so a human or agent discovers and
invokes any tool by its logical name:

    python3 .tropo/scripts/tropo.py list                          # what's on the wall   (≈ MCP tools/list)
    python3 .tropo/scripts/tropo.py query-events --party <uid>    # reach for it by name (≈ MCP tools/call)
    python3 .tropo/scripts/tropo.py call query-events --limit 5   # explicit call form
    python3 .tropo/scripts/tropo.py help query-events            # forward --help to the tool
    python3 .tropo/scripts/tropo.py schema [<name>]              # MCP-shaped JSON catalog (what L2 serves)
    python3 .tropo/scripts/tropo.py doctor                       # discoverability health + backfill backlog

DESIGN — L1 as close to MCP as a server-less CLI can be (Mike-A90):
  * `list`   ≈ MCP tools/list   (name + description + invocation)
  * `call`   ≈ MCP tools/call   (name + arguments -> result)
  * `schema` emits the SAME {name, description, inputSchema} catalog an L2 MCP
             server would serve over the wire — one definition, two surfaces.

Catalog source: the tool files' OWN frontmatter (NOT registry.jsonl, whose
extraction currently flattens name->uid). Reading source-of-truth means the
dispatcher works in a freshly-unzipped Studio with no rebuild and no server —
preserving the L1 "download a zip, point an LLM at it" promise.

Zero hard dependencies: prefers PyYAML if present (canonical-library pin), and
degrades to a minimal scalar frontmatter scan so it runs in a Studio without
pyyaml. Pure stdlib otherwise.

Canonical dispatcher since v1.64.0 (Talos T12, tool-discovery-l1 cycle per
dev-spec b7d4f1a9). Promoted from the A90 prototype after: name backfill across
the full catalog (0 uid-only tools), tool.capsule v1.7 validator ratchet landed,
shim-supersession documented. The .tropo/scripts/query-events.py and
emit-event.py shims remain as discoverable-name aliases; retire-on-adoption when
agents uniformly reach for `tropo <name>` instead.
"""
import sys
import json
import subprocess
from pathlib import Path

# This file lives at <vault-root>/.tropo/scripts/tropo.py
VAULT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = VAULT_ROOT / "vault" / "tools"

# Source extensions we can run, in invocation-preference order.
RUNNERS = {
    ".py": [sys.executable],
    ".js": ["node"],
    ".sh": ["bash"],
}

# Frontmatter scalar keys the dispatcher surfaces (MCP-shaped projection).
_SCALAR_KEYS = (
    "uid", "name", "type", "transport", "implementation_kind",
    "cli_command", "status", "owner", "domain", "title", "description",
)


def _parse_frontmatter(text):
    """Return the leading frontmatter block as a dict.

    Tools carry frontmatter two ways:
      * bare markdown head:        ---\\n ... \\n---
      * python-script docstring:   \"\"\"---\\n ... \\n---\"\"\"  (tool.capsule v1.6 §2.5)
    A fence line is `---` possibly wrapped in the docstring quotes, so we strip
    surrounding quotes before comparing. Prefer PyYAML; fall back to a minimal
    scalar-only scan (discovery needs no nested structures).
    """
    def is_fence(ln):
        return ln.strip().strip('"').strip("'").strip() == "---"

    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines[:120]):
        if is_fence(ln):
            start = i
            break
    if start is None:
        return {}
    end = None
    for j in range(start + 1, min(len(lines), start + 400)):
        if is_fence(lines[j]):
            end = j
            break
    if end is None:
        return {}
    block = "\n".join(lines[start + 1:end])

    try:
        import yaml  # canonical library when available
        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    out = {}
    for ln in block.splitlines():
        if not ln or ln[0] in (" ", "\t", "#", "-"):
            continue
        if ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        key = key.strip()
        if key in _SCALAR_KEYS:
            out[key] = val.strip().strip('"').strip("'")
    return out


def load_catalog():
    """Scan vault/tools/ and return a list of tool records (dicts)."""
    catalog = []
    if not TOOLS_DIR.is_dir():
        return catalog
    for path in sorted(TOOLS_DIR.iterdir()):
        if path.suffix not in RUNNERS:
            continue
        uid = path.stem
        try:
            fm = _parse_frontmatter(path.read_text(errors="replace"))
        except Exception:
            fm = {}
        name = str(fm.get("name") or "").strip()
        named = bool(name) and name != uid
        transport = str(fm.get("transport") or "")
        catalog.append({
            "uid": uid,
            "name": name or uid,
            "named": named,                 # has a real logical name (not just the uid)
            "path": str(path.relative_to(VAULT_ROOT)),
            "ext": path.suffix,
            "transport": transport,
            "cli_command": str(fm.get("cli_command") or ""),
            "status": str(fm.get("status") or ""),
            "owner": str(fm.get("owner") or ""),
            "description": str(fm.get("domain") or fm.get("description")
                               or fm.get("title") or "").strip(),
        })
    return catalog


def resolve(catalog, token):
    """Resolve a name-or-uid token to a tool record. Exact name wins, then uid."""
    by_name = {r["name"]: r for r in catalog if r["named"]}
    if token in by_name:
        return by_name[token]
    by_uid = {r["uid"]: r for r in catalog}
    if token in by_uid:
        return by_uid[token]
    norm = token.lower().replace("_", "-")
    for r in catalog:
        if r["named"] and r["name"].lower().replace("_", "-") == norm:
            return r
    return None


def run_tool(rec, args):
    runner = RUNNERS.get(rec["ext"], [sys.executable])
    target = VAULT_ROOT / rec["path"]
    return subprocess.run(runner + [str(target)] + list(args)).returncode


def cmd_list(catalog, _args):
    active = [r for r in catalog if r["status"] in ("", "active")]
    named = sorted([r for r in active if r["named"]], key=lambda r: r["name"])
    unnamed = [r for r in active if not r["named"]]
    print("tropo tools — %d active (%d named, %d uid-only)\n"
          % (len(active), len(named), len(unnamed)))
    width = max([len(r["name"]) for r in named], default=12)
    for r in named:
        print("  %-*s  %s" % (width, r["name"], (r["description"] or "(no description)")[:92]))
    if unnamed:
        print("\n  uid-only (no logical name yet — see `tropo doctor`):")
        for r in unnamed:
            print("    %s  %s" % (r["uid"], (r["description"] or "")[:66]))
    print("\nrun:  tropo <name> [args]   |   tropo call <name> [args]   |   tropo help <name>\n"
          "note: .tropo/scripts/query-events.py and emit-event.py are name-alias shims;\n"
          "      retire-on-adoption when agents uniformly use `tropo <name>`")
    return 0


def cmd_help(catalog, args):
    if not args:
        print(__doc__)
        return 0
    rec = resolve(catalog, args[0])
    if not rec:
        print("tropo: unknown tool %r (try `tropo list`)" % args[0])
        return 2
    return run_tool(rec, ["--help"])


def cmd_schema(catalog, args):
    """Emit the MCP-shaped catalog: [{name, description, inputSchema, _tropo}].

    This is the shape an L2 MCP `tools/list` would serve. inputSchema is
    forward-declared here (the cli_command carries human invocation today); the
    formal cycle derives full JSON Schema per tool.
    """
    recs = catalog
    if args:
        rec = resolve(catalog, args[0])
        recs = [rec] if rec else []
    out = []
    for r in recs:
        if not r:
            continue
        out.append({
            "name": r["name"],
            "description": r["description"],
            "inputSchema": {"type": "object",
                            "x-cli-command": r["cli_command"] or None,
                            "x-status": "forward-declared"},
            "_tropo": {"uid": r["uid"], "transport": r["transport"] or "cli",
                       "path": r["path"]},
        })
    print(json.dumps(out, indent=2))
    return 0


def cmd_doctor(catalog, _args):
    total = len(catalog)
    named = [r for r in catalog if r["named"]]
    unnamed = [r for r in catalog if not r["named"]]
    # cli_command is required only for transport:cli tools (library/mcp/etc. are exempt)
    no_cli = [r for r in catalog
              if not r["cli_command"] and r.get("transport", "").lower() in ("", "cli")]
    seen, dupes = {}, []
    for r in named:
        seen.setdefault(r["name"], []).append(r["uid"])
    for nm, uids in seen.items():
        if len(uids) > 1:
            dupes.append((nm, uids))
    pct = (100 * len(named) / total) if total else 0
    print("tropo doctor — tool-discovery health\n")
    print("  catalog: %d tools" % total)
    print("  named  : %d  (%.0f%%)" % (len(named), pct))
    print("  uid-only (capsule `name:` defaults to uid — BACKFILL BACKLOG): %d" % len(unnamed))
    print("  missing cli_command: %d" % len(no_cli))
    if dupes:
        print("  DUPLICATE logical names:")
        for nm, uids in dupes:
            print("    %s -> %s" % (nm, ", ".join(uids)))
    if unnamed:
        print("\n  backfill backlog (need a logical `name:` per tool.capsule v1.6):")
        for r in unnamed:
            print("    %s  (%s)" % (r["uid"], r["path"]))
    print("\n  -> backfill + a tool.capsule validator ratchet (WARN->ERROR on "
          "name==uid) is the formal cycle's work (brief a3e9f1c7).")
    return 0


COMMANDS = {
    "list": cmd_list, "ls": cmd_list,
    "help": cmd_help,
    "schema": cmd_schema,
    "doctor": cmd_doctor,
}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    catalog = load_catalog()
    cmd = argv[0]
    if cmd in COMMANDS:
        return COMMANDS[cmd](catalog, argv[1:])
    if cmd == "call":
        if len(argv) < 2:
            print("tropo call: need a tool name")
            return 2
        rec = resolve(catalog, argv[1])
        if not rec:
            print("tropo: unknown tool %r (try `tropo list`)" % argv[1])
            return 2
        return run_tool(rec, argv[2:])
    # bare form: `tropo <name> [args]`  (MCP tools/call ergonomics)
    rec = resolve(catalog, cmd)
    if rec:
        return run_tool(rec, argv[1:])
    print("tropo: unknown command or tool %r\n  try: tropo list | tropo help | "
          "tropo <name> [args]" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
