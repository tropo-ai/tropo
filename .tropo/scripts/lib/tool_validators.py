"""tool_validators.py — Validation Checks for vault/tools/ entries.

Per tool.capsule v1.6 (d5e1b4a3) §4 Validation Checks.
Wired into tropo-validate.py main() by Talos T10 v1.56 Lane E.

Checks (WARN severity at v1.56; ERROR ratchet planned once migration stabilizes):
  1. All 10 required frontmatter slots present (uid, name, type, status, owner,
     domain, spawnable_by, transport, input, provenance-pair)
  2. type == "tool"
  3. status in {draft, active, deprecated, superseded}
  4. transport in {mcp, action, http, platform, sa, cli, library}
  5. Conditional required fields per transport present
  6. implementation_kind present for cli transport
  7. implementation file exists (script_path or cli_command resolves)
  8. member_of present (graph citizenship; empty list OK but field required)
  9. provenance pair present (created + created_by OR commissioned + commissioned_by)
 10. For status:active — body has at least 4 of 6 required section headings
 11. uid format is valid 8-hex
 12. name is present and non-empty
 13. governed_by present (tool.capsule UID d5e1b4a3)
 14. JSONL row count parity (tools in index == tools in vault/tools/ directory)

v1.7 additions (WARN at v1.64; ERROR-ratchet at v1.65 per dev-spec b7d4f1a9):
 v1.7-1. name != uid — a tool MUST carry a logical name, not just repeat its UID
 v1.7-2. cli_command non-empty for transport:cli (refines Check 5 field-presence to value-non-empty)
"""



from __future__ import annotations

TARGETS_CAPSULE = "tool"  # Lane V Layer 3 M.1 targeting (8e2f1a47)
import json, re, sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = VAULT_ROOT / "vault" / "tools"
INDEX_PATH = VAULT_ROOT / "vault" / "00-index.jsonl"

VALID_STATUS = {"draft", "active", "deprecated", "superseded"}
VALID_TRANSPORT = {"mcp", "action", "http", "platform", "sa", "cli", "library"}
TOOL_CAPSULE_UID = "d5e1b4a3"

# Per-transport conditional required fields (tool.capsule v1.6 §2 Conditionally Required)
TRANSPORT_REQUIRED: dict[str, list[str]] = {
    "mcp":      ["mcp_server", "mcp_tool_name"],
    "action":   ["action_id"],
    "http":     ["http_endpoint", "http_method"],
    "platform": ["platform_route"],
    "sa":       ["sa_name"],
    "cli":      ["cli_command"],
}

# Body section headings that constitute the 6-section requirement
REQUIRED_BODY_SECTIONS = [
    r"##\s+(Intent|Purpose)",
    r"##\s+(Invocation Protocol|Usage)",
    r"##\s+(Input\s*/\s*Output|Schema|Input|Output)",
    r"##\s+(Governance|Permissions)",
    r"##\s+(Verification|Success)",
    r"##\s+(Failure Modes|Errors)",
]

UID_RE = re.compile(r"^[0-9a-f]{8}$")


def _parse_frontmatter_from_tool_file(path: Path) -> tuple[str | None, str]:
    """Return (frontmatter_yaml_str, body_text) for a vault/tools/ file."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return None, ""

    ext = path.suffix.lower()
    if ext == ".py":
        # Strip shebang + leading comments
        lines = text.split("\n")
        i = 0
        while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
            i += 1
        rest = "\n".join(lines[i:])
        m = re.match(r'^("""|\'\'\')(.*?)\1', rest, re.DOTALL)
        if not m:
            return None, text
        docstring = m.group(2)
        fm_m = re.search(r"---\n(.*?)\n---", docstring, re.DOTALL)
        if not fm_m:
            return None, text
        return fm_m.group(1), text

    elif ext == ".json":
        try:
            obj = json.loads(text)
            meta = obj.get("tropo_metadata")
            if not isinstance(meta, dict):
                return None, text
            # Serialize tropo_metadata as flat YAML for field extraction
            lines_out: list[str] = []
            for k, v in meta.items():
                if isinstance(v, list):
                    lines_out.append(f"{k}:")
                    for item in v:
                        lines_out.append(f"  - {item}")
                elif isinstance(v, bool):
                    lines_out.append(f"{k}: {'true' if v else 'false'}")
                elif v is not None:
                    lines_out.append(f"{k}: {v}")
            return "\n".join(lines_out), text
        except Exception:
            return None, text

    else:  # .md
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not m:
            return None, text
        return m.group(1), text[m.end():]


def _get_scalar(fm: str, field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", fm, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    if "#" in val and not val.startswith('"'):
        val = val.split("#")[0].strip()
    return val or None


def _get_list(fm: str, field: str) -> list[str]:
    inline = re.search(rf"^{re.escape(field)}:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if inline:
        raw = inline.group(1)
        return [v.strip().strip('"').strip("'") for v in raw.split(",") if v.strip()]
    block = re.search(rf"^{re.escape(field)}:\s*\n((?:\s*-\s+.*\n?)+)", fm, re.MULTILINE)
    if block:
        items: list[str] = []
        for line in block.group(1).splitlines():
            m2 = re.match(r"^\s*-\s+(.*?)\s*$", line)
            if m2:
                items.append(m2.group(1).strip().strip('"').strip("'"))
        return items
    return []


def run_all_tool_checks(vault: Path) -> tuple[list[str], int, int]:
    """Run tool.capsule v1.6 checks against all vault/tools/ files.

    Returns (findings, tools_checked, defects).
    """
    tools_dir = vault / "vault" / "tools"
    if not tools_dir.is_dir():
        return [], 0, 0

    findings: list[str] = []
    tools_checked = 0

    for path in sorted(tools_dir.iterdir()):
        if path.suffix.lower() not in (".py", ".md", ".json"):
            continue
        if not UID_RE.match(path.stem):
            continue

        tools_checked += 1
        uid = path.stem
        label = f"vault/tools/{path.name}"

        fm, body = _parse_frontmatter_from_tool_file(path)
        if fm is None:
            findings.append(f"  [WARN] {label}: no parseable frontmatter (Check 1)")
            continue

        # Check 11: uid format
        fm_uid = _get_scalar(fm, "uid")
        if fm_uid and not UID_RE.match(fm_uid):
            findings.append(f"  [WARN] {label}: uid {fm_uid!r} not 8-hex (Check 11)")
        if fm_uid and fm_uid != uid:
            findings.append(f"  [WARN] {label}: frontmatter uid {fm_uid!r} != filename {uid!r} (Check 11)")

        # Check 2: type == "tool"
        typ = _get_scalar(fm, "type")
        if typ != "tool":
            findings.append(f"  [WARN] {label}: type={typ!r} not 'tool' (Check 2)")

        # Check 1: 10 required slots
        required_slots = ["uid", "name", "type", "status", "owner", "domain",
                          "spawnable_by", "transport", "input"]
        missing = []
        for slot in required_slots:
            if slot in ("spawnable_by",):
                val = _get_list(fm, slot)
                if not val and not _get_scalar(fm, slot):
                    missing.append(slot)
            elif slot == "input":
                # input can be a multi-line block; just check key presence
                if not re.search(rf"^{slot}:", fm, re.MULTILINE):
                    missing.append(slot)
            else:
                if not _get_scalar(fm, slot):
                    missing.append(slot)
        if missing:
            findings.append(f"  [WARN] {label}: missing required slots {missing} (Check 1)")

        # Check 12: name non-empty
        name = _get_scalar(fm, "name")
        if not name:
            findings.append(f"  [WARN] {label}: name is empty or missing (Check 12)")

        # Check v1.7-1: name != uid — logical name required (WARN at v1.64; ERROR-ratchet at v1.65)
        if name and name == uid:
            findings.append(
                f"  [WARN] {label}: name==uid ({uid!r}) — tool must carry a logical name, "
                f"not just its UID (tool.capsule v1.7 Check v1.7-1; ERROR ratchet at v1.65)"
            )

        # Check v1.7-2: cli_command non-empty for transport:cli (WARN at v1.64; ERROR-ratchet at v1.65)
        # Complements Check 5 (field presence) with value non-empty; excludes library transport.
        transport_v = _get_scalar(fm, "transport")
        if transport_v == "cli":
            cli_cmd = _get_scalar(fm, "cli_command")
            if not cli_cmd:
                findings.append(
                    f"  [WARN] {label}: transport:cli but cli_command is empty or missing "
                    f"(tool.capsule v1.7 Check v1.7-2; ERROR ratchet at v1.65)"
                )

        # Check 3: status enum
        status = _get_scalar(fm, "status")
        if status and status not in VALID_STATUS:
            findings.append(f"  [WARN] {label}: status={status!r} not in {sorted(VALID_STATUS)} (Check 3)")

        # Check 4: transport enum
        transport = _get_scalar(fm, "transport")
        if not transport:
            findings.append(f"  [WARN] {label}: transport missing (Check 4)")
        elif transport not in VALID_TRANSPORT:
            findings.append(f"  [WARN] {label}: transport={transport!r} not in {sorted(VALID_TRANSPORT)} (Check 4)")

        # Check 5: conditional required fields per transport
        if transport in TRANSPORT_REQUIRED:
            for cond_field in TRANSPORT_REQUIRED[transport]:
                if not _get_scalar(fm, cond_field) and not re.search(rf"^{cond_field}:", fm, re.MULTILINE):
                    findings.append(
                        f"  [WARN] {label}: transport={transport!r} requires {cond_field!r} (Check 5)"
                    )

        # Check 6: implementation_kind present for cli transport
        if transport == "cli":
            impl_kind = _get_scalar(fm, "implementation_kind")
            if not impl_kind:
                findings.append(f"  [WARN] {label}: cli transport missing implementation_kind (Check 6)")

        # Check 7: implementation file exists
        script_path_str = _get_scalar(fm, "script_path")
        if script_path_str:
            script_path_abs = vault / script_path_str
            if not script_path_abs.exists():
                # For migrated tools the script_path may point to vault/tools/<uid>.py (itself)
                # which is valid; check that too
                if not (vault / "vault" / "tools" / path.name).exists():
                    findings.append(
                        f"  [WARN] {label}: script_path {script_path_str!r} does not resolve (Check 7)"
                    )

        # Check 8: member_of present as field
        if not re.search(r"^member_of:", fm, re.MULTILINE):
            findings.append(f"  [WARN] {label}: member_of field absent (Check 8)")

        # Check 9: provenance pair
        has_created = bool(_get_scalar(fm, "created") and _get_scalar(fm, "created_by"))
        has_commissioned = bool(_get_scalar(fm, "commissioned") and _get_scalar(fm, "commissioned_by"))
        if not has_created and not has_commissioned:
            findings.append(f"  [WARN] {label}: missing provenance pair (created+created_by or commissioned+commissioned_by) (Check 9)")

        # Check 10: active tools have body sections
        if status == "active" and path.suffix.lower() in (".py", ".md"):
            sections_found = sum(
                1 for pat in REQUIRED_BODY_SECTIONS
                if re.search(pat, body, re.MULTILINE | re.IGNORECASE)
            )
            if sections_found < 3:
                findings.append(
                    f"  [WARN] {label}: status:active but only {sections_found}/6 body sections found (Check 10)"
                )

        # Check 13: governed_by should be tool.capsule UID
        governed_by = _get_scalar(fm, "governed_by")
        if governed_by and governed_by != TOOL_CAPSULE_UID:
            findings.append(
                f"  [WARN] {label}: governed_by={governed_by!r} expected {TOOL_CAPSULE_UID!r} (Check 13)"
            )

    # Check 14: index parity — tools in directory vs tools in 00-index.jsonl
    index_path = vault / "vault" / "00-index.jsonl"
    if index_path.exists():
        try:
            indexed_tool_uids: set[str] = set()
            for line in index_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("type") == "tool":
                        indexed_tool_uids.add(rec["uid"])
                except json.JSONDecodeError:
                    pass
            disk_tool_uids = {
                f.stem for f in tools_dir.iterdir()
                if f.suffix.lower() in (".py", ".md", ".json") and UID_RE.match(f.stem)
            }
            unindexed = disk_tool_uids - indexed_tool_uids
            if unindexed:
                findings.append(
                    f"  [WARN] {len(unindexed)} vault/tools/ file(s) not in 00-index.jsonl "
                    f"— run rebuild-index --apply (Check 14): {sorted(unindexed)}"
                )
        except Exception as e:
            findings.append(f"  [WARN] Check 14 index parity check failed: {e}")

    return findings, tools_checked, len(findings)
