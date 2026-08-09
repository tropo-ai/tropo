"""Single-source parser for a capsule's §Template leg (Governed Autonomy S2, bba40cd7).

Shared by tropo-mint-id.py (stamps the scaffold) and tropo-check-one.py (verifies
placeholder consumption) so the two tools can never read the contract differently
-- per the Template-Leg Contract v1.0 (b933eafb): "the template is the single
source ... stamped verbatim, never hand-copied."

Format (contract-fixed): a "## §Template" section containing a ~~~markdown-fenced
scaffold (frontmatter + body). <<MINT:*>> tokens are the only substitutions mint
performs. <!-- REQUIRED: --> placeholders must be consumed by the authoring work;
survival is deterministic INCOMPLETE. <!-- OPTIONAL: --> placeholders may be
deleted; survival is a WARN-grade untidiness at most.

Enforcement start (`template_enforced_from`, optionally refined by
`template_enforced_from_version`): the leg is a MINT-TIME contract. An entry that
predates its type's leg or a revised body-contract version was never stamped from
that scaffold, so it cannot be judged against it -- the Mike-walked program brief
(b600698e §6) puts the pre-existing corpus on the protect list ("they gain
template/verifier legs, nothing migrates") and S2's own scope (bba40cd7) names
historical migration OUT. Grandfathering is read straight from capsule metadata,
with no derived registry and no runtime git dependency (a shipped customer
studio has no git history).

Severity (`instance_verifier_severity`): the generic instance-verifier tier's
grades are declared once, on the capsule-of-capsules, and read from there. No
tool carries a second copy -- a duplicated grade is what silently drifts.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

CAPSULE_DEFINITION_CAPSULE = "tropo-capsule-definition.capsule.md"
MINT_REGISTRY_REL = Path("vault/capsules/mint-registry.json")
MINT_TEMPLATE_HOME_REL = Path("vault/capsules/templates")
MINT_REGISTRY_SCHEMA_VERSION = 2
MINT_MODES = frozenset({"human", "system-only", "disabled"})
MINT_BINDING_FIELDS = (
    "mint_template",
    "mint_template_version",
    "mint_template_sha256",
    "mint_output_home",
)
MINT_TOKEN_NAMES = frozenset(
    {"uid", "date", "author", "capsule_version", "activation_uid"}
)
SYSTEM_CONTEXT_TOKEN_RE = re.compile(r"<<SYSTEM:([a-z_]+)>>")

#: Generic-tier check names the instance verifier grades. The GRADES live on the
#: capsule (§Generic Instance-Verifier Checks); only the NAMES live here, because
#: they are the code's own call sites rather than a governance decision.
INSTANCE_VERIFIER_CHECKS = (
    "sections-present",
    "placeholder-survival",
    "stray-mint-token",
    "body-unreadable",
)

SEVERITY_BLOCK_RE = re.compile(
    r"^instance_verifier_severity:[ \t]*\n(?P<body>(?:[ \t]+\S.*\n?)+)", re.MULTILINE
)
SEVERITY_ENTRY_RE = re.compile(
    r"^[ \t]+(?P<check>[a-z-]+):[ \t]*(?P<severity>WARN|FAIL|ERROR)[ \t]*$", re.MULTILINE
)
ENFORCED_FROM_RE = re.compile(
    r"^[ \t]*template_enforced_from:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?\s*$", re.MULTILINE
)
ENFORCED_FROM_VERSION_RE = re.compile(
    r"^[ \t]*template_enforced_from_version:\s*['\"]?(\d+\.\d+(?:\.\d+)?)['\"]?\s*$",
    re.MULTILINE,
)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")

MINT_TOKEN_RE = re.compile(r"<<MINT:([a-z_]+)>>")
MINT_TOKEN_OPEN = "<<MINT:"
REQUIRED_PLACEHOLDER_RE = re.compile(r"<!--\s*REQUIRED:\s*(.*?)\s*-->")
OPTIONAL_PLACEHOLDER_RE = re.compile(r"<!--\s*OPTIONAL:\s*(.*?)\s*-->")
SECTION_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.MULTILINE)
ENUM_HINT_RE = re.compile(r"^([a-zA-Z_][\w]*):\s*.*?#\s*one of:\s*(.+)$")

TEMPLATE_HEADING_RE = re.compile(r"^##[ \t]+§Template\b.*$", re.MULTILINE)
FENCE_RE = re.compile(r"~~~markdown\s*\n(.*?)\n~~~", re.DOTALL)


class TemplateLegError(ValueError):
    """No capsule governs the type, or the capsule has no usable §Template leg.

    Both are refusal paths per the closed-registry rule (walked Q1 law) -- the
    message names the governance path a caller should follow, never just "not found".
    """


def _semver_tuple(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = SEMVER_RE.fullmatch(value)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


@dataclass
class TemplateLeg:
    capsule_path: Path
    capsule_type: str
    capsule_version: str
    scaffold: str            # raw fenced scaffold text (frontmatter + body), tokens intact
    frontmatter_text: str    # scaffold's frontmatter block, without the --- delimiters
    body_text: str           # scaffold's body (everything after the closing ---)
    enforced_from: str | None = None   # capsule's declared `template_enforced_from`
    template_path: Path | None = None
    template_version: str | None = None
    output_home: Path | None = None
    mint_mode: str = "disabled"
    enforced_from_version: str | None = None

    def grandfathers(
        self,
        created: str | None,
        capsule_version: object = None,
    ) -> bool:
        """True when this instance predates the leg and so must NOT be judged
        against it -- it could not have been minted from a scaffold that did not
        exist yet.

        A capsule may declare ``template_enforced_from_version`` when a revised
        scaffold changes its body contract. A parseable older instance version
        is then grandfathered regardless of authoring date, while an instance at
        or above the floor is governed by the revised scaffold.

        Three date edge cases, each resolved toward "do not manufacture a false
        positive", because a false MISSING-SECTION is indistinguishable from a
        real one and buries the real ones:

        1. Capsule declares no `template_enforced_from` -> grandfather everything.
           We cannot date the scaffold, so we cannot date any instance against it.
           The caller reports the undeclared capsule once, loudly, so the gap is
           visible rather than silent; declaring the field turns enforcement on.
        2. Instance carries no `created` date -> grandfather. `created` is a
           core-required field, so its absence is already reported by the
           required-frontmatter check; re-reporting it as body shape would double-
           count one defect as many.
        3. Instance created exactly ON the declared date -> grandfather. The
           declaration has one-day granularity, so a same-day instance cannot be
           shown to have had the scaffold available when it was written (both
           same-day cases in this vault -- a hand-authored runbook and a Python
           script -- were false positives). Enforcement begins strictly after.
        """
        floor = _semver_tuple(self.enforced_from_version)
        instance_version = _semver_tuple(capsule_version)
        if floor is not None and instance_version is not None:
            return instance_version < floor
        if not self.enforced_from:
            return True
        if not created:
            return True
        return str(created) <= self.enforced_from

    def _section_spans(self, text: str) -> list[tuple[str, str]]:
        """(heading_text, chunk_through_next_heading) for every heading in text,
        skipping headings whose own text IS a placeholder (e.g. the H1 title line
        '# <!-- REQUIRED: title --> ') -- those are caught by flat placeholder
        scanning, not section-presence checking; a placeholder-titled heading has
        no fixed name to check an instance against."""
        headings = [(m.start(), m.group(2).strip()) for m in SECTION_HEADING_RE.finditer(text)]
        spans = []
        for i, (start, title) in enumerate(headings):
            if REQUIRED_PLACEHOLDER_RE.search(title) or OPTIONAL_PLACEHOLDER_RE.search(title):
                continue
            end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            spans.append((title, text[start:end]))
        return spans

    def required_sections(self) -> list[str]:
        """Fixed-title headings whose chunk (through the next heading) contains at
        least one REQUIRED placeholder -- these must survive, by exact title, in
        any instance minted from this leg (deletion = visible MISSING-SECTION).

        "Minted from this leg" is the whole scope: pair this with grandfathers()
        before reporting, or the mint-time contract gets applied retroactively to
        entries written before the scaffold existed."""
        return [title for title, chunk in self._section_spans(self.body_text)
                if REQUIRED_PLACEHOLDER_RE.search(chunk)]

    def optional_sections(self) -> list[str]:
        """Fixed-title headings marked OPTIONAL and carrying no REQUIRED placeholder
        of their own -- deletion is normal, not a defect."""
        return [title for title, chunk in self._section_spans(self.body_text)
                if OPTIONAL_PLACEHOLDER_RE.search(chunk) and not REQUIRED_PLACEHOLDER_RE.search(chunk)]

    def enum_hints(self) -> dict[str, list[str]]:
        """field -> allowed values, from inline '# one of: a | b | c' comments in
        the frontmatter template (the contract's stated enum-hint mechanism).
        Best-effort: only fields carrying the literal hint are checked; fields
        stamped with a fixed legal-birth default (no inline hint) are not."""
        hints: dict[str, list[str]] = {}
        for line in self.frontmatter_text.splitlines():
            m = ENUM_HINT_RE.match(line)
            if m:
                hints[m.group(1)] = [v.strip() for v in m.group(2).split("|")]
        return hints


def capsule_path_for_type(vault_root: Path, type_name: str) -> Path:
    return vault_root / "vault" / "capsules" / f"tropo-{type_name}.capsule.md"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _frontmatter_mapping(text: str, path: Path) -> dict:
    if not text.startswith("---\n"):
        raise TemplateLegError(f"{path.name} has no leading YAML frontmatter block")
    end = text.find("\n---", 4)
    if end == -1:
        raise TemplateLegError(f"{path.name}'s YAML frontmatter block is unterminated")
    try:
        value = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise TemplateLegError(f"{path.name} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(value, dict):
        raise TemplateLegError(f"{path.name}'s YAML frontmatter is not a mapping")
    return value


def _studio_relative_path(vault_root: Path, raw: object, field: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise TemplateLegError(f"{field} must be a non-empty Studio-relative path")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise TemplateLegError(f"{field} {raw!r} is not a canonical Studio-relative path")
    if rel.as_posix() != raw:
        raise TemplateLegError(f"{field} {raw!r} is not canonical POSIX path syntax")
    resolved = (vault_root / rel).resolve()
    try:
        resolved.relative_to(vault_root.resolve())
    except ValueError as exc:
        raise TemplateLegError(f"{field} {raw!r} escapes the Studio root") from exc
    return rel


def _strict_regular_file(
    vault_root: Path,
    rel: Path,
    field: str,
    *,
    home: Path | None = None,
) -> Path:
    """Return a root-contained regular file without following symlink components."""
    root = vault_root.resolve(strict=True)
    if rel.is_absolute():
        raise TemplateLegError(f"{field} must be Studio-relative")
    logical = vault_root / rel
    cursor = vault_root
    try:
        for part in rel.parts:
            cursor = cursor / part
            mode = cursor.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise TemplateLegError(f"{field} {rel.as_posix()!r} contains a symlink")
    except FileNotFoundError as exc:
        raise TemplateLegError(f"{field} is missing at {rel.as_posix()}") from exc
    except OSError as exc:
        raise TemplateLegError(f"{field} cannot be inspected at {rel.as_posix()}: {exc}") from exc
    if not stat.S_ISREG(logical.lstat().st_mode):
        raise TemplateLegError(f"{field} {rel.as_posix()!r} is not a regular file")
    resolved = logical.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise TemplateLegError(f"{field} {rel.as_posix()!r} escapes the Studio root") from exc
    if home is not None:
        try:
            resolved.relative_to((vault_root / home).resolve(strict=True))
        except ValueError as exc:
            raise TemplateLegError(
                f"{field} must live under {home.as_posix()}"
            ) from exc
    return logical


def _strict_directory(
    vault_root: Path,
    rel: Path,
    field: str,
) -> Path:
    """Return a root-contained directory without following symlink components."""
    root = vault_root.resolve(strict=True)
    if rel.is_absolute():
        raise TemplateLegError(f"{field} must be Studio-relative")
    logical = vault_root / rel
    cursor = vault_root
    try:
        for part in rel.parts:
            cursor = cursor / part
            mode = cursor.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise TemplateLegError(f"{field} {rel.as_posix()!r} contains a symlink")
    except FileNotFoundError as exc:
        raise TemplateLegError(f"{field} is missing at {rel.as_posix()}") from exc
    except OSError as exc:
        raise TemplateLegError(
            f"{field} cannot be inspected at {rel.as_posix()}: {exc}"
        ) from exc
    if not stat.S_ISDIR(logical.lstat().st_mode):
        raise TemplateLegError(f"{field} {rel.as_posix()!r} is not a directory")
    resolved = logical.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise TemplateLegError(f"{field} {rel.as_posix()!r} escapes the Studio root") from exc
    return logical


def _mint_token_names(scaffold: str, source: object) -> set[str]:
    """Return token names while rejecting every malformed ``<<MINT:`` form."""
    names: set[str] = set()
    cursor = 0
    while True:
        start = scaffold.find(MINT_TOKEN_OPEN, cursor)
        if start == -1:
            break
        match = MINT_TOKEN_RE.match(scaffold, start)
        if match is None:
            end = scaffold.find("\n", start)
            if end == -1:
                end = min(len(scaffold), start + 80)
            rendered = scaffold[start:end]
            raise TemplateLegError(
                f"{source} has malformed mint token form {rendered!r}; "
                "expected <<MINT:lowercase_name>>"
            )
        names.add(match.group(1))
        cursor = match.end()
    return names


def _exact_mint_tokens(scaffold: str, source: object) -> None:
    tokens = _mint_token_names(scaffold, source)
    unknown = sorted(tokens - MINT_TOKEN_NAMES)
    missing = sorted(MINT_TOKEN_NAMES - tokens)
    if unknown or missing:
        details = []
        if unknown:
            details.append(f"unknown {unknown}")
        if missing:
            details.append(f"missing {missing}")
        raise TemplateLegError(
            f"{source} has an invalid mint token set ({'; '.join(details)}); "
            f"exactly {sorted(MINT_TOKEN_NAMES)} are required"
        )


def _capsule_registry_rows(vault_root: Path) -> list[dict]:
    capsules_rel = Path("vault/capsules")
    capsules_dir = vault_root / capsules_rel
    if not capsules_dir.is_dir():
        raise TemplateLegError(f"capsule directory is missing at {capsules_rel}")
    rows: list[dict] = []
    seen: dict[str, Path] = {}
    for capsule_path in sorted(capsules_dir.glob("tropo-*.capsule.md")):
        capsule_rel = capsule_path.relative_to(vault_root)
        capsule_path = _strict_regular_file(
            vault_root, capsule_rel, "capsule_path"
        )
        raw = capsule_path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TemplateLegError(f"{capsule_rel} is not UTF-8") from exc
        fm = _frontmatter_mapping(text, capsule_path)
        if fm.get("type") != "capsule-definition":
            continue
        filename_type = capsule_path.name.removeprefix("tropo-").removesuffix(
            ".capsule.md"
        )
        declared_name = fm.get("name")
        type_name = (
            declared_name
            if isinstance(declared_name, str) and declared_name
            else filename_type
        )
        if declared_name not in (None, "") and declared_name != filename_type:
            raise TemplateLegError(
                f"{capsule_path.name} declares name {declared_name!r}, "
                f"which disagrees with filename type {filename_type!r}"
            )
        if type_name in seen:
            raise TemplateLegError(
                f"duplicate capsule type {type_name!r}: "
                f"{seen[type_name].name} and {capsule_path.name}"
            )
        seen[type_name] = capsule_path
        if "mintable" in fm:
            raise TemplateLegError(
                f"{capsule_path.name} uses retired boolean mintable; "
                "declare mint_mode: human | system-only | disabled"
            )
        mint_mode = fm.get("mint_mode", "disabled")
        if mint_mode not in MINT_MODES:
            raise TemplateLegError(
                f"{capsule_path.name} has invalid mint_mode {mint_mode!r}"
            )
        capsule_version = str(fm.get("version", ""))
        if not capsule_version:
            raise TemplateLegError(
                f"{capsule_path.name} has no version for registry binding"
            )
        row = {
            "type": type_name,
            "mint_mode": mint_mode,
            "capsule_path": capsule_rel.as_posix(),
            "capsule_version": capsule_version,
            "capsule_sha256": _sha256(raw),
        }
        if mint_mode != "disabled":
            missing = [
                field
                for field in MINT_BINDING_FIELDS
                if field not in fm or fm[field] in (None, "")
            ]
            if missing:
                raise TemplateLegError(
                    f"{capsule_path.name} is {mint_mode} but missing binding "
                    f"field(s) {missing}"
                )
            template_rel = _studio_relative_path(
                vault_root, fm["mint_template"], "mint_template"
            )
            template_path = _strict_regular_file(
                vault_root,
                template_rel,
                "mint_template",
                home=MINT_TEMPLATE_HOME_REL,
            )
            template_raw = template_path.read_bytes()
            declared_hash = str(fm["mint_template_sha256"])
            if not re.fullmatch(r"[0-9a-f]{64}", declared_hash):
                raise TemplateLegError(
                    f"{capsule_path.name} mint_template_sha256 is not 64 lowercase hex"
                )
            if declared_hash != _sha256(template_raw):
                raise TemplateLegError(
                    f"{capsule_path.name} companion hash drift: declared "
                    f"{declared_hash}, actual {_sha256(template_raw)}"
                )
            try:
                scaffold = template_raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TemplateLegError(
                    f"companion template {template_rel} is not UTF-8"
                ) from exc
            _exact_mint_tokens(scaffold, template_rel)
            _studio_relative_path(
                vault_root, fm["mint_output_home"], "mint_output_home"
            )
            _strict_directory(
                vault_root,
                Path(str(fm["mint_output_home"])),
                "mint_output_home",
            )
            row.update(
                {
                    field: (
                        str(fm[field])
                        if field
                        in ("mint_template_version", "mint_template_sha256")
                        else fm[field]
                    )
                    for field in MINT_BINDING_FIELDS
                }
            )
        rows.append(row)
    return sorted(rows, key=lambda row: row["type"])


def build_mint_registry_bytes(vault_root: Path) -> bytes:
    """Build the deterministic, clock-free schema-v2 registry."""
    registry = {
        "generated_by": "argus-a144",
        "schema_version": MINT_REGISTRY_SCHEMA_VERSION,
        "source": "vault/capsules/tropo-*.capsule.md frontmatter",
        "types": _capsule_registry_rows(vault_root),
    }
    return (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_mint_registry(vault_root: Path) -> list[dict]:
    """Load and prove the ahead-of-time registry is byte-current."""
    try:
        path = _strict_regular_file(
            vault_root, MINT_REGISTRY_REL, "mint registry"
        )
    except TemplateLegError as exc:
        raise TemplateLegError(
            f"mint registry is missing at {MINT_REGISTRY_REL.as_posix()} — "
            "regenerate it with `python3 vault/tools/tropo-generate-mint-registry.py`"
        ) from exc
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TemplateLegError(f"mint registry at {MINT_REGISTRY_REL} is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MINT_REGISTRY_SCHEMA_VERSION:
        raise TemplateLegError(
            f"mint registry at {MINT_REGISTRY_REL} has an unsupported schema_version"
        )
    rows = value.get("types")
    if not isinstance(rows, list):
        raise TemplateLegError(f"mint registry at {MINT_REGISTRY_REL} has no types list")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("type"), str):
            raise TemplateLegError(f"mint registry at {MINT_REGISTRY_REL} has a malformed type row")
        type_name = row["type"]
        if type_name in seen:
            raise TemplateLegError(f"mint registry has duplicate type {type_name!r}")
        seen.add(type_name)
        if row.get("mint_mode") not in MINT_MODES:
            raise TemplateLegError(
                f"mint registry type {type_name!r} has invalid mint_mode"
            )
    expected = build_mint_registry_bytes(vault_root)
    if raw != expected:
        raise TemplateLegError(
            f"mint registry at {MINT_REGISTRY_REL} is stale; regenerate it before "
            "listing or minting"
        )
    return rows


def list_mintable_types(vault_root: Path) -> list[str]:
    """Backward-compatible library name; returns human-mintable types only."""
    return sorted(
        row["type"]
        for row in load_mint_registry(vault_root)
        if row["mint_mode"] == "human"
    )


def _load_bound_mint_template(
    vault_root: Path, type_name: str, *, required_mode: str
) -> TemplateLeg:
    """Resolve one registry-selected companion and verify only its binding.

    The generated registry is the fast type-selection surface. Once selected,
    the capsule and companion hashes plus every flat binding field are checked
    before any UID is minted or output path is touched. Embedded §Template legs
    are deliberately not consulted here.
    """
    rows = load_mint_registry(vault_root)
    row = next((candidate for candidate in rows if candidate["type"] == type_name), None)
    if row is None:
        expected = capsule_path_for_type(vault_root, type_name)
        if expected.is_file():
            raise TemplateLegError(
                f"type {type_name!r} is governed but absent from the generated mint registry — "
                "regenerate the registry; mint refuses stale type selection"
            )
        raise TemplateLegError(
            f"unknown type {type_name!r}: no capsule or generated mint binding exists"
        )
    if row["mint_mode"] != required_mode:
        raise TemplateLegError(
            f"type {type_name!r} has mint_mode {row['mint_mode']!r}, not "
            f"{required_mode!r}"
        )

    required_registry_fields = (
        "capsule_path",
        "capsule_version",
        "capsule_sha256",
        *MINT_BINDING_FIELDS,
    )
    missing = [field for field in required_registry_fields if field not in row]
    if missing:
        raise TemplateLegError(
            f"mint registry binding for {type_name!r} is incomplete: missing {missing}"
        )

    capsule_rel = _studio_relative_path(
        vault_root, row["capsule_path"], "registry capsule_path"
    )
    capsule_path = vault_root / capsule_rel
    capsule_path = _strict_regular_file(
        vault_root, capsule_rel, f"selected capsule for {type_name!r}"
    )
    capsule_raw = capsule_path.read_bytes()
    if _sha256(capsule_raw) != row["capsule_sha256"]:
        raise TemplateLegError(
            f"stale capsule hash for {type_name!r}; regenerate "
            f"{MINT_REGISTRY_REL.as_posix()} before minting"
        )
    try:
        capsule_text = capsule_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TemplateLegError(f"selected capsule {capsule_rel} is not UTF-8") from exc
    capsule_fm = _frontmatter_mapping(capsule_text, capsule_path)
    if capsule_fm.get("name") != type_name:
        raise TemplateLegError(
            f"selected capsule {capsule_rel} declares name {capsule_fm.get('name')!r}, "
            f"not {type_name!r}"
        )
    if str(capsule_fm.get("version")) != str(row["capsule_version"]):
        raise TemplateLegError(
            f"capsule version drift for {type_name!r}; regenerate the mint registry"
        )
    if capsule_fm.get("mint_mode", "disabled") != required_mode:
        raise TemplateLegError(
            f"capsule binding drift for {type_name!r}: mint_mode changed"
        )
    for field in MINT_BINDING_FIELDS:
        if str(capsule_fm.get(field)) != str(row[field]):
            raise TemplateLegError(
                f"capsule binding drift for {type_name!r}: {field} does not match "
                "the generated mint registry"
            )

    template_rel = _studio_relative_path(
        vault_root, row["mint_template"], "mint_template"
    )
    template_path = _strict_regular_file(
        vault_root,
        template_rel,
        f"companion template for {type_name!r}",
        home=MINT_TEMPLATE_HOME_REL,
    )
    template_raw = template_path.read_bytes()
    template_hash = _sha256(template_raw)
    if template_hash != row["mint_template_sha256"]:
        raise TemplateLegError(
            f"stale template hash for {type_name!r}; update the capsule binding and "
            "regenerate the mint registry before minting"
        )
    try:
        scaffold = template_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TemplateLegError(f"companion template {template_rel} is not UTF-8") from exc
    _exact_mint_tokens(scaffold, template_rel)
    if not scaffold.startswith("---\n"):
        raise TemplateLegError(
            f"companion template {template_rel} does not open with YAML frontmatter"
        )
    end = scaffold.find("\n---", 4)
    if end == -1:
        raise TemplateLegError(
            f"companion template {template_rel} has unterminated YAML frontmatter"
        )
    output_home = _studio_relative_path(
        vault_root, row["mint_output_home"], "mint_output_home"
    )
    _strict_directory(vault_root, output_home, "mint_output_home")
    capsule_frontmatter = _capsule_frontmatter(
        capsule_text, capsule_path.name
    )
    enforced = ENFORCED_FROM_RE.search(capsule_frontmatter)
    enforced_version = ENFORCED_FROM_VERSION_RE.search(capsule_frontmatter)
    return TemplateLeg(
        capsule_path=capsule_path,
        capsule_type=type_name,
        capsule_version=str(row["capsule_version"]),
        scaffold=scaffold,
        frontmatter_text=scaffold[4:end],
        body_text=scaffold[end + 4:],
        enforced_from=enforced.group(1) if enforced else None,
        template_path=template_path,
        template_version=str(row["mint_template_version"]),
        output_home=output_home,
        mint_mode=required_mode,
        enforced_from_version=(
            enforced_version.group(1) if enforced_version else None
        ),
    )


def load_mint_template(vault_root: Path, type_name: str) -> TemplateLeg:
    """Load a human-mintable template; system-only and disabled types refuse."""
    return _load_bound_mint_template(
        vault_root, type_name, required_mode="human"
    )


def load_system_mint_template(vault_root: Path, type_name: str) -> TemplateLeg:
    """Explicit lifecycle-writer seam for a system-only template."""
    return _load_bound_mint_template(
        vault_root, type_name, required_mode="system-only"
    )


def load_verifier_template(vault_root: Path, type_name: str) -> TemplateLeg:
    """Use a bound companion for human/system types; legacy disabled types embed."""
    capsule_path = capsule_path_for_type(vault_root, type_name)
    if capsule_path.exists() or capsule_path.is_symlink():
        capsule_rel = capsule_path.relative_to(vault_root)
        capsule_path = _strict_regular_file(
            vault_root,
            capsule_rel,
            f"capsule for verifier type {type_name!r}",
        )
        capsule_fm = _frontmatter_mapping(
            capsule_path.read_text(encoding="utf-8"), capsule_path
        )
        mode = capsule_fm.get("mint_mode", "disabled")
        if mode == "human":
            return load_mint_template(vault_root, type_name)
        if mode == "system-only":
            return load_system_mint_template(vault_root, type_name)
        if mode != "disabled":
            raise TemplateLegError(
                f"capsule {capsule_path.name} has invalid mint_mode {mode!r}"
            )
    return load_template_leg(vault_root, type_name)


def load_instance_verifier_severities(vault_root: Path) -> dict[str, str]:
    """Read the generic instance-verifier tier's declared grades from the
    capsule-of-capsules (38c63381) §Generic Instance-Verifier Checks.

    Same shape as the `enforced_enums` idiom (core.capsule §Governance Rule 8):
    the capsule declares, the validator reads it straight from the capsule -- no
    derived registry, no second copy in tool code to drift out of sync.

    Returns {check_name: 'WARN'|'FAIL'|'ERROR'} for whatever the capsule declares.
    A name the capsule does not declare is simply absent; callers refuse to grade
    it rather than substituting a private default, because a private default is
    the second source of truth this whole mechanism exists to prevent.
    """
    path = vault_root / "vault" / "capsules" / CAPSULE_DEFINITION_CAPSULE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    fm_end = text.find("\n---", 3) if text.startswith("---") else -1
    if fm_end == -1:
        return {}
    block = SEVERITY_BLOCK_RE.search(text[:fm_end])
    if not block:
        return {}
    return {
        m.group("check"): m.group("severity")
        for m in SEVERITY_ENTRY_RE.finditer(block.group("body"))
    }


def _capsule_frontmatter(capsule_text: str, capsule_name: str) -> str:
    if not capsule_text.startswith("---"):
        raise TemplateLegError(f"capsule {capsule_name} has no leading frontmatter block")
    end = capsule_text.find("\n---", 3)
    if end == -1:
        raise TemplateLegError(f"capsule {capsule_name}'s frontmatter block is unterminated")
    return capsule_text[:end]


def _parse_capsule_version(capsule_text: str, capsule_name: str) -> str:
    fm = _capsule_frontmatter(capsule_text, capsule_name)
    m = re.search(r"^[ \t]*version:\s*['\"]?([\w.]+)['\"]?\s*$", fm, re.MULTILINE)
    if not m:
        raise TemplateLegError(f"capsule {capsule_name} has no version: field in its frontmatter")
    return m.group(1)


def load_template_leg(vault_root: Path, type_name: str) -> TemplateLeg:
    """Resolve type -> capsule -> §Template leg, or raise TemplateLegError naming
    the governance path: no capsule -> propose a three-legged capsule (Mike locks);
    capsule but no §Template -> the leg is missing, un-mintable until authored."""
    path = capsule_path_for_type(vault_root, type_name)
    if not path.exists() and not path.is_symlink():
        raise TemplateLegError(
            f"no capsule governs type {type_name!r} (expected "
            f"{path.relative_to(vault_root)}). The registry is closed (Governed "
            f"Autonomy S2, walked Q1 law): propose a three-legged capsule (schema + "
            f"template + verifier) -- Mike locks it."
        )
    path = _strict_regular_file(
        vault_root,
        path.relative_to(vault_root),
        f"capsule for legacy type {type_name!r}",
    )
    capsule_text = path.read_text(encoding="utf-8")
    capsule_version = _parse_capsule_version(capsule_text, path.name)

    heading = TEMPLATE_HEADING_RE.search(capsule_text)
    if not heading:
        raise TemplateLegError(
            f"capsule {path.name} governs type {type_name!r} but has no §Template "
            f"leg -- un-mintable until one is authored per the Template-Leg Contract "
            f"(b933eafb)."
        )
    # First fenced block AFTER the heading -- not "up to the next ## heading", since
    # the scaffold's own body legitimately contains "## " sub-headings inside the
    # fence (a naive heading-bounded search truncates at the first one of those).
    fence = FENCE_RE.search(capsule_text, heading.end())
    if not fence:
        raise TemplateLegError(
            f"capsule {path.name}'s §Template section has no ~~~markdown-fenced "
            f"scaffold -- malformed leg, not the contract's format."
        )
    scaffold = fence.group(1)

    if not scaffold.startswith("---\n"):
        raise TemplateLegError(
            f"capsule {path.name}'s §Template scaffold does not open with a "
            f"frontmatter block ('---') -- malformed leg."
        )
    end = scaffold.find("\n---", 4)
    if end == -1:
        raise TemplateLegError(
            f"capsule {path.name}'s §Template scaffold has an unterminated "
            f"frontmatter block."
        )
    frontmatter_text = scaffold[4:end]
    body_text = scaffold[end + 4:]

    capsule_frontmatter = _capsule_frontmatter(capsule_text, path.name)
    enforced = ENFORCED_FROM_RE.search(capsule_frontmatter)
    enforced_version = ENFORCED_FROM_VERSION_RE.search(capsule_frontmatter)

    return TemplateLeg(
        capsule_path=path,
        capsule_type=type_name,
        capsule_version=capsule_version,
        scaffold=scaffold,
        frontmatter_text=frontmatter_text,
        body_text=body_text,
        enforced_from=enforced.group(1) if enforced else None,
        enforced_from_version=(
            enforced_version.group(1) if enforced_version else None
        ),
    )


def stamp(
    leg: TemplateLeg,
    *,
    uid: str,
    date: str,
    author: str,
    activation_uid: str | None,
) -> str:
    """Substitute the exact universal token set -- the ONLY substitutions mint
    performs per the contract -- and return the finished instance text. An
    unknown token name is a malformed leg (ERROR), never silently skipped."""
    _exact_mint_tokens(leg.scaffold, leg.template_path or leg.capsule_path.name)
    tokens = {
        "uid": uid,
        "date": date,
        "author": json.dumps(author, ensure_ascii=False),
        "capsule_version": leg.capsule_version,
        "activation_uid": (
            json.dumps(activation_uid, ensure_ascii=False)
            if activation_uid
            else "null"
        ),
    }

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in tokens:
            raise TemplateLegError(
                f"unknown mint token <<MINT:{key}>> in {leg.capsule_path.name} -- "
                f"the token set is fixed ({sorted(MINT_TOKEN_NAMES)}); a leg "
                f"using anything else is malformed."
            )
        return tokens[key]

    return MINT_TOKEN_RE.sub(_sub, leg.scaffold)


def stamp_system_template(
    leg: TemplateLeg,
    *,
    uid: str,
    date: str,
    author: str,
    context: dict[str, str],
    activation_uid: str | None = None,
) -> str:
    """Stamp a loaded system-only scaffold with lifecycle-owned context."""
    if leg.mint_mode != "system-only":
        raise TemplateLegError("stamp_system_template requires a system-only leg")
    names = set(SYSTEM_CONTEXT_TOKEN_RE.findall(leg.scaffold))
    missing = sorted(names - set(context))
    extra = sorted(set(context) - names)
    if missing or extra:
        raise TemplateLegError(
            f"system context mismatch: missing {missing}, extra {extra}"
        )
    stamped = stamp(
        leg,
        uid=uid,
        date=date,
        author=author,
        activation_uid=activation_uid,
    )
    return SYSTEM_CONTEXT_TOKEN_RE.sub(
        lambda match: json.dumps(context[match.group(1)], ensure_ascii=False),
        stamped,
    )


#: A closed fence of either flavour, with its info string. Unclosed fences are
#: deliberately NOT matched: a fence that never closes is malformed markdown, and
#: granting it an exemption would let one stray backtick hide the rest of a file.
ANY_FENCE_RE = re.compile(
    r"^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)[^\n]*$",
    re.MULTILINE | re.DOTALL,
)

#: Types whose own body carries template tokens BY DESIGN. A capsule-definition
#: MUST show the scaffold it governs, tokens intact, or it cannot declare a
#: contract at all.
_TEMPLATE_BEARING_TYPES = frozenset({"capsule-definition"})


def _blank(text: str, start: int, end: int) -> str:
    """Replace a span with same-length whitespace, preserving newlines.

    Blanked rather than deleted on purpose. Deleting a span joins the text on
    either side of it, which can splice two harmless fragments into something
    that scans as a token; and every offset after the cut moves, so a finding's
    reported position stops describing the file on disk.
    """
    span = text[start:end]
    return text[:start] + "".join(c if c == "\n" else " " for c in span) + text[end:]


def scannable_instance_text(
    instance_text: str, entry_type: "str | None" = None
) -> str:
    """The regions of an instance where a surviving token is a real defect.

    For every type but the template-bearing ones this is the whole text, so
    behaviour is unchanged and the default argument keeps it that way for
    callers that have no type in hand.

    For a `capsule-definition` it excludes the entry's own §Template leg and its
    fenced blocks. Those tokens are the CONTRACT, not an unfilled instance:
    scanning them reported every capsule as incompletely minted, which was 228
    of the shipped box's 235 health-check failures and 238 identical findings
    studio-side across the same 14 UIDs (metis-g105 diagnosis, punch-list
    51dc85ef item 1, 2026-08-08).

    What still reds, and must: a token or REQUIRED placeholder in ordinary prose
    of a capsule-definition, outside both the template leg and any fence. The
    exclusion is by REGION, never by type alone — a type-wide skip would have
    been two lines shorter and would have made the check unable to fail for the
    exact files it exists to check.
    """
    if entry_type not in _TEMPLATE_BEARING_TYPES:
        return instance_text

    text = instance_text

    # Fences FIRST, and the order is load-bearing. A scaffold is markdown inside
    # a fence, so it contains its own headings -- `# <!-- REQUIRED: title -->` is
    # the first line of most of them. Looking for the end of the §Template
    # section before blanking fences finds one of THOSE headings and ends the
    # section on its opening line, leaving the whole scaffold in scope. Measured
    # while building this: fences-second dropped 169 of 238 studio findings and
    # left 69 across 13 capsules; fences-first drops all 238.
    for fence in list(ANY_FENCE_RE.finditer(text)):
        text = _blank(text, fence.start(), fence.end())

    # Then the §Template leg itself: from its heading to the next heading at the
    # same level or higher, or end of file. Read against the fence-blanked text,
    # so only real section headings can close it. This catches what the fences
    # do not -- unfenced scaffold prose and changelog rows that carry tokens.
    heading = TEMPLATE_HEADING_RE.search(text)
    if heading is not None:
        end = len(text)
        for candidate in SECTION_HEADING_RE.finditer(text, heading.end()):
            if len(candidate.group(1)) <= 2:
                end = candidate.start()
                break
        text = _blank(text, heading.start(), end)

    return text


def find_required_placeholders(
    instance_text: str, entry_type: "str | None" = None
) -> list[str]:
    scannable = scannable_instance_text(instance_text, entry_type)
    return [m.group(1) for m in REQUIRED_PLACEHOLDER_RE.finditer(scannable)]


def find_stray_mint_tokens(
    instance_text: str, entry_type: "str | None" = None
) -> list[str]:
    # Blanking preserves length and offsets, so the scan below is byte-for-byte
    # the scan that ran before this argument existed.
    scannable = scannable_instance_text(instance_text, entry_type)
    forms: list[str] = []
    cursor = 0
    while True:
        start = scannable.find(MINT_TOKEN_OPEN, cursor)
        if start == -1:
            break
        match = MINT_TOKEN_RE.match(scannable, start)
        if match is not None:
            forms.append(match.group(0))
            cursor = match.end()
            continue
        end = scannable.find(">>", start)
        if end == -1:
            end = scannable.find("\n", start)
            if end == -1:
                end = min(len(scannable), start + 80)
        else:
            end += 2
        form = scannable[start:end]
        # The star wildcard is documentation convention for "any mint token" and can
        # never be a real token: the grammar (MINT_TOKEN_RE) admits only [a-z_]+, so
        # `<<MINT:*>>` in prose is always vocabulary talk, never an unfilled instance.
        # Proven by talos-t40 (evt 9552, 2026-08-08); suppression ruled by metis-g105
        # after the in-box binary gate made the two wildcard mentions the sole reds.
        # Exact form only — every other malformed `<<MINT:` shape still reports.
        if form != "<<MINT:*>>":
            forms.append(form)
        cursor = max(end, start + len(MINT_TOKEN_OPEN))
    return forms


def find_sections(instance_text: str) -> set[str]:
    return {m.group(2).strip() for m in SECTION_HEADING_RE.finditer(instance_text)}
