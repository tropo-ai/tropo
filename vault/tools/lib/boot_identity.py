"""lib/boot_identity.py -- soul resolution as a FACT ABOUT FILES, not a claim
by the agent whose soul it is.

Why this exists (f015b61d2291 AC1, and Darin's line from the v1.95 external
test: *"Do not build any part of this system on an agent's self-report of its
own compliance"*).

The canonical activation playbook resolved identity two ways -- Shape A
(`agent_uid:` -> the `§Soul` section of `vault/agents/<uid>.md`) and Shape B (a
Tier-3 `soul_letter:`). Neither resolves for the THREE-FILE agents that
`vault/skills/tropo-create-executive-agent.md` actually creates for a customer:
those declare `charter_file:` and carry their soul in the charter. A cold walker
built "sage" strictly by that skill and its run journal fired `Context Loaded`
with Step 2.0 never entered -- a compliant agent, a lookup table with no row
that matched. This module is that row, plus the two shapes the live studio
already uses that no prose ever wrote down.

Four shapes, tried in order, first hit wins:

  A  `agent_uid:`               -> `vault/agents/<uid>.md` §Soul
                                   (redirect stubs are followed to §Boot-Extension)
  C  `charter_file:`            -> the charter's `soul:` frontmatter block,
                                   plus its `## Identity` body if present
  D  `charter_uid:`             -> `vault/files/<uid>.md` §Soul / `## N. SOUL`,
                                   falling back to the charter's `soul:` block
  B  `soul_letter:` (Tier 3)    -> the declared per-file soul letter

WARN-SAFE, absolutely: nothing here refuses, halts, or returns a nonzero
disposition that a caller is expected to treat as a stop. The worst outcome is
`not_resolved`, which is a LOUD NAMED finding the agent relays and then
continues booting. A missing soul is better than a halted activation, and a
missing soul that nobody can see is worse than both -- that is the defect this
module exists to end.

Stdlib only, and no `yaml` import: this runs at Group 0/2 of a boot, on a fresh
customer box, on the 3.9 interpreter floor, before anything has been installed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Activation-file discovery
# ---------------------------------------------------------------------------

# Three live spellings. The playbook's own "Activation file definition" rule
# named only the first and third through v1.95; `<slug>-activate.md` is what
# jules / nestor / tiphys actually use, so a resolver that trusts the prose
# reports "no activation file" for three agents that have one.
ACTIVATION_SPELLINGS = (
    "{slug}-activation.md",
    "{slug}-activate.md",
    "activate.md",
)

SOUL_TITLES = ("soul", "soul letter", "identity")

# Values a shipped template leaves for a founder to fill. Deliberately an
# explicit list plus one structural rule (a frontmatter scalar that is entirely
# `[...]`), never a broad `\[...\]` regex -- markdown links are square brackets
# and a resolver that calls every link a placeholder is a false-alarm generator.
PLACEHOLDER_MARKERS = (
    "<FILL",
    "[Core value",
    "[Named role",
    "[Communication style",
    "[How this agent handles ambiguity",
    "[Brief context about this agent",
    "[One-line role description",
    "[agent-name]",
    "[Agent Name]",
    "[founder-name]",
    "[uid as minted",
    # The `## Identity` body of the shipped charter template, verbatim. Found
    # by the end-to-end run: filling only the `soul:` frontmatter left this
    # paragraph reading "You are **Sage**, [role] for [team/organization
    # name]" and the resolver called it `resolved`. A soul-loaded verdict over
    # a paragraph that still says [role] is a false green, and a false green
    # here is the exact species of defect this whole change exists to end.
    "[role]",
    "[team/organization name]",
    "[2-3 sentences describing who this agent is",
)

BRACKETED_SCALAR = re.compile(r"^\[[^\]]+\]$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _norm_title(raw: str) -> str:
    """`## §Soul`, `## 4. SOUL`, `## Identity` all normalize to one key."""
    t = raw.strip().lstrip("#").strip()
    t = t.lstrip("§").strip()
    t = re.sub(r"^\d+[.)]\s*", "", t)
    return t.strip().strip(":").lower()


# ---------------------------------------------------------------------------
# Frontmatter -- a deliberately small parser for the shapes boot files use
# ---------------------------------------------------------------------------


def _scalar(raw: str) -> str:
    v = raw.strip()
    if v[:1] in ("'", '"'):
        q = v[0]
        end = v.find(q, 1)
        if end != -1:
            return v[1:end]
        return v[1:]
    # Strip a trailing ` # comment` only when unquoted.
    v = re.split(r"\s+#", v, maxsplit=1)[0]
    return v.strip()


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Top-level scalars, plus one level of nested mapping/list (enough for
    `soul:` / `capability_scope:`). Unknown shapes are ignored, never fatal."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    body: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        body.append(line)

    out: Dict[str, Any] = {}
    i = 0
    while i < len(body):
        line = body[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if rest.strip():
            out[key] = _scalar(rest)
            i += 1
            continue
        # Block: gather the indented region beneath it.
        i += 1
        block: List[str] = []
        while i < len(body):
            nxt = body[i]
            if nxt.strip() and not nxt[:1].isspace():
                break
            block.append(nxt)
            i += 1
        out[key] = _parse_block(block)
    return out


def _parse_block(block: List[str]) -> Any:
    items: List[str] = []
    mapping: Dict[str, Any] = {}
    pending: Optional[str] = None
    for line in block:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- "):
            val = _scalar(s[2:])
            if pending is not None:
                if isinstance(mapping.get(pending), list):
                    mapping[pending].append(val)
            else:
                items.append(val)
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_\-]*):\s*(.*)$", s)
        if m:
            k, rest = m.group(1), m.group(2)
            if rest.strip():
                mapping[k] = _scalar(rest)
                pending = None
            else:
                mapping[k] = []
                pending = k
    if mapping:
        return mapping
    return items


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------


def extract_section(text: str, titles: Tuple[str, ...]) -> Optional[Tuple[str, str]]:
    """Return (matched heading line, body) for the BEST heading whose
    normalized title is in `titles`.

    Best, not first, and the difference is a false pass caught by the live
    sweep before this shipped: a unified entry carries `## 1. IDENTITY` inside
    `§Charter` at line 55 and the real `## §Soul` at line 159, so a
    first-match rule reported six of this studio's agents as souls-loaded
    while handing them their charter's identity paragraph instead. Ranking is
    (a) position in `titles` -- "soul" outranks "identity" -- then (b) a
    `§`-prefixed section marker outranks a plain heading of the same title.

    Terminator rule, equally load-bearing on real substrate: a `§`-prefixed
    heading is a UNIFIED-ENTRY SECTION MARKER, so it ends only at the next
    `§` heading. Argus's `## §Soul` opens with an `# This Is Who We Are` two
    lines in; the obvious "next heading of any shallower level" rule reports
    his 7.8k-char soul as empty. A plain heading (a charter's `## Identity`)
    ends at the next heading of the same or shallower level.
    """
    lines = text.splitlines()
    best: Optional[Tuple[int, int, int, int, bool]] = None
    for idx, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        title = _norm_title(m.group(2))
        if title not in titles:
            continue
        marker = m.group(2).strip().startswith("§")
        rank = (titles.index(title), 0 if marker else 1, idx)
        cand = (rank[0], rank[1], rank[2], len(m.group(1)), marker)
        if best is None or cand[:3] < best[:3]:
            best = cand
    if best is None:
        return None
    start, level, is_section_marker = best[2], best[3], best[4]

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        m = HEADING.match(lines[idx])
        if not m:
            continue
        if is_section_marker:
            if m.group(2).strip().startswith("§"):
                end = idx
                break
        elif len(m.group(1)) <= level:
            end = idx
            break
    return lines[start], "\n".join(lines[start + 1 : end]).strip()


def _is_redirect_stub(body: str) -> bool:
    """Talos's `§Soul` is three lines saying the soul is inline in
    `§Boot-Extension`. Reporting that stub as a loaded soul is a false pass."""
    if len(body) > 400:
        return False
    low = body.lower()
    return "boot-extension" in low and (
        "no separate soul" in low or "authored inline" in low
    )


# ---------------------------------------------------------------------------
# Placeholders
# ---------------------------------------------------------------------------


def find_placeholders(
    text: str, soul_block: Optional[Dict[str, Any]] = None
) -> List[str]:
    hits: List[str] = []
    for marker in PLACEHOLDER_MARKERS:
        if marker in text:
            hits.append(marker)
    if isinstance(soul_block, dict):
        for key, val in soul_block.items():
            vals = val if isinstance(val, list) else [val]
            for v in vals:
                if isinstance(v, str) and BRACKETED_SCALAR.match(v.strip()):
                    hits.append("soul.{}".format(key))
                    break
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

STATUS_RESOLVED = "resolved"
STATUS_PLACEHOLDER = "resolved_placeholder"
STATUS_NOT_RESOLVED = "not_resolved"
STATUS_NOT_COMMISSIONED = "not_commissioned"
STATUS_NO_ACTIVATION = "no_activation_file"


@dataclass
class Resolution:
    agent: str
    status: str
    shape: Optional[str] = None
    source: Optional[str] = None
    section: Optional[str] = None
    text: str = ""
    placeholders: List[str] = field(default_factory=list)
    tried: List[Tuple[str, str]] = field(default_factory=list)
    activation_file: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self.status in (STATUS_RESOLVED, STATUS_PLACEHOLDER)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "shape": self.shape,
            "source": self.source,
            "section": self.section,
            "chars": len(self.text),
            "placeholders": self.placeholders,
            "tried": ["{}: {}".format(s, w) for s, w in self.tried],
            "activation_file": self.activation_file,
        }


def find_activation_file(vault_root: Path, slug: str) -> Optional[Path]:
    folder = Path(vault_root) / "agents" / slug
    for spelling in ACTIVATION_SPELLINGS:
        cand = folder / spelling.format(slug=slug)
        if cand.is_file():
            return cand
    return None


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_soul(vault_root: Path, slug: str) -> Resolution:
    """Resolve `slug`'s soul from files on disk. Never raises for a missing or
    malformed file; every dead end becomes a named `tried` entry the caller
    prints, so an unresolved soul says WHICH shapes were attempted and why each
    failed rather than going quiet."""
    root = Path(vault_root)
    act_path = find_activation_file(root, slug)
    if act_path is None:
        return Resolution(
            agent=slug,
            status=STATUS_NO_ACTIVATION,
            tried=[
                (
                    "activation",
                    "no {} under agents/{}/".format(
                        " / ".join(s.format(slug=slug) for s in ACTIVATION_SPELLINGS),
                        slug,
                    ),
                )
            ],
        )

    act_text = _read(act_path) or ""
    fm = parse_frontmatter(act_text)
    act_rel = _rel(act_path, root)
    tried: List[Tuple[str, str]] = []

    # An uncommissioned placeholder has no soul BY DESIGN. Alarming on a
    # healthy declared state is how a founder learns to stop reading alarms.
    if str(fm.get("placeholder", "")).lower() == "true" or str(
        fm.get("current_agent_status", "")
    ).lower() in ("not-commissioned", "not_commissioned"):
        return Resolution(
            agent=slug,
            status=STATUS_NOT_COMMISSIONED,
            activation_file=act_rel,
            tried=[
                ("placeholder", "activation declares an uncommissioned placeholder")
            ],
        )

    # --- Shape A -----------------------------------------------------------
    agent_uid = fm.get("agent_uid")
    if agent_uid:
        entry = root / "vault" / "agents" / "{}.md".format(agent_uid)
        text = _read(entry)
        if text is None:
            tried.append(
                (
                    "A",
                    "agent_uid: {} -> vault/agents/{}.md is unreadable/absent".format(
                        agent_uid, agent_uid
                    ),
                )
            )
        else:
            found = extract_section(text, SOUL_TITLES)
            if found is None:
                tried.append(
                    ("A", "vault/agents/{}.md has no §Soul section".format(agent_uid))
                )
            else:
                heading, body = found
                section = heading.strip()
                if _is_redirect_stub(body):
                    alt = extract_section(text, ("boot-extension",))
                    if alt and alt[1].strip():
                        heading, body = alt
                        section = "{} (via §Soul redirect)".format(alt[0].strip())
                if body.strip():
                    return Resolution(
                        agent=slug,
                        status=STATUS_RESOLVED,
                        shape="A",
                        source="vault/agents/{}.md".format(agent_uid),
                        section=section,
                        text=body,
                        placeholders=find_placeholders(body),
                        tried=tried,
                        activation_file=act_rel,
                    )
                tried.append(
                    ("A", "§Soul in vault/agents/{}.md is empty".format(agent_uid))
                )
    else:
        tried.append(("A", "activation declares no agent_uid:"))

    # --- Shape C -----------------------------------------------------------
    # The three-file end-user standard. This is the row that was missing.
    charter_file = fm.get("charter_file")
    if charter_file:
        cpath = root / str(charter_file)
        ctext = _read(cpath)
        if ctext is None:
            tried.append(
                ("C", "charter_file: {} is unreadable/absent".format(charter_file))
            )
        else:
            res = _from_charter(
                slug, ctext, str(charter_file), "C", act_rel, tried
            )
            if res is not None:
                return res
    else:
        tried.append(("C", "activation declares no charter_file:"))

    # --- Shape D -----------------------------------------------------------
    # Live in this studio (silas, jules): the charter is a governed vault entry
    # addressed by uid, and silas's soul is `## 4. SOUL` inside it.
    charter_uid = fm.get("charter_uid")
    if charter_uid:
        rel = "vault/files/{}.md".format(charter_uid)
        ctext = _read(root / rel)
        if ctext is None:
            tried.append(
                ("D", "charter_uid: {} -> {} is unreadable/absent".format(charter_uid, rel))
            )
        else:
            res = _from_charter(slug, ctext, rel, "D", act_rel, tried)
            if res is not None:
                return res
    else:
        tried.append(("D", "activation declares no charter_uid:"))

    # --- Shape B -----------------------------------------------------------
    soul_letter = fm.get("soul_letter")
    if not soul_letter:
        ext_text = _read(root / "agents" / slug / "agent-boot.extension.md")
        if ext_text is not None:
            soul_letter = parse_frontmatter(ext_text).get("soul_letter")
    if soul_letter:
        stext = _read(root / str(soul_letter))
        if stext is None:
            tried.append(
                ("B", "soul_letter: {} is unreadable/absent".format(soul_letter))
            )
        elif stext.strip():
            return Resolution(
                agent=slug,
                status=STATUS_RESOLVED,
                shape="B",
                source=str(soul_letter),
                section="(whole file)",
                text=stext,
                placeholders=find_placeholders(stext),
                tried=tried,
                activation_file=act_rel,
            )
        else:
            tried.append(("B", "soul_letter: {} is empty".format(soul_letter)))
    else:
        tried.append(("B", "no Tier-3 soul_letter: declared"))

    return Resolution(
        agent=slug,
        status=STATUS_NOT_RESOLVED,
        tried=tried,
        activation_file=act_rel,
    )


def _from_charter(
    slug: str,
    ctext: str,
    rel: str,
    shape: str,
    act_rel: str,
    tried: List[Tuple[str, str]],
) -> Optional[Resolution]:
    """A charter carries identity in TWO places and both are real substrate:
    the structured `soul:` frontmatter block that
    `vault/templates/tropo-executive-charter.template.md` guarantees, and a
    `## Identity` / `## N. SOUL` body section. Read the frontmatter block
    FIRST -- it is a machine-readable declaration in the file we already have
    open, so a founder who renames a heading does not lose their agent's soul."""
    cfm = parse_frontmatter(ctext)
    soul_block = cfm.get("soul") if isinstance(cfm.get("soul"), dict) else None
    found = extract_section(ctext, SOUL_TITLES)

    parts: List[str] = []
    sections: List[str] = []
    if soul_block:
        parts.append(
            "soul: (frontmatter)\n"
            + json.dumps(soul_block, indent=2, ensure_ascii=False)
        )
        sections.append("soul: frontmatter block")
    if found and found[1].strip() and not _is_redirect_stub(found[1]):
        parts.append(found[0] + "\n" + found[1])
        sections.append(found[0].strip())

    if not parts:
        tried.append(
            (
                shape,
                "{} has neither a soul: frontmatter block nor a body section titled {}".format(
                    rel, "/".join(SOUL_TITLES)
                ),
            )
        )
        return None

    text = "\n\n".join(parts)
    placeholders = find_placeholders(text, soul_block)
    return Resolution(
        agent=slug,
        status=STATUS_PLACEHOLDER if placeholders else STATUS_RESOLVED,
        shape=shape,
        source=rel,
        section=" + ".join(sections),
        text=text,
        placeholders=placeholders,
        tried=tried,
        activation_file=act_rel,
    )
