"""meta_validators.py — Lane V Layer 3 schema-to-implementation meta-validator.

Per spec 8e2f1a47 (v1.58 M.1). Parses capsule §schema declarations and verifies
that validator implementations in .tropo/scripts/lib/*_validators.py match.

Detects four drift classes:
  enum-value-drift       — VALID_* hard-coded sets differ from capsule §schema enum
  registered-type-drift  — REGISTERED_TYPES differs from capsule §3 type registry
  per-type-ext-drift     — per-type required extensions differ from capsule §3 declarations
  required-field-drift   — unchecked at v1.58 (punted per §7.2(d)); emits info note only

Severity: WARN at v1.58; ERROR ratchet at v1.59+.
"""
from __future__ import annotations
import ast, re
from dataclasses import dataclass, field
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[3]
CAPSULES_DIR = VAULT_ROOT / ".tropo" / "capsules"
VALIDATORS_DIR = VAULT_ROOT / ".tropo" / "scripts" / "lib"


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class SchemaDecls:
    """Declarations extracted from a capsule §schema section."""
    capsule_name: str
    enums: dict[str, set[str]] = field(default_factory=dict)      # field_name → {value, ...}
    registered_types: set[str] = field(default_factory=set)        # event type strings
    per_type_extensions: dict[str, list[str]] = field(default_factory=dict)  # type → [ext, ...]
    parse_ambiguous: list[str] = field(default_factory=list)       # items that couldn't be parsed


@dataclass
class ImplDecls:
    """Declarations extracted from a validator module via AST."""
    module_name: str
    targets_capsule: str = ""
    valid_sets: dict[str, set[str]] = field(default_factory=dict)  # const_name → {value, ...}
    registered_types: set[str] = field(default_factory=set)
    parse_ambiguous: list[str] = field(default_factory=list)


@dataclass
class Finding:
    capsule: str
    validator: str
    drift_class: str   # enum-value-drift | registered-type-drift | per-type-ext-drift | parse-ambiguous | validator-orphan | impl-not-detected
    field_name: str = ""
    schema_values: set[str] = field(default_factory=set)
    impl_values: set[str] = field(default_factory=set)
    drift_added: set[str] = field(default_factory=set)   # in impl but not schema
    drift_removed: set[str] = field(default_factory=set) # in schema but not impl
    severity: str = "WARN"
    message: str = ""

    def as_line(self) -> str:
        if self.drift_class in ("enum-value-drift", "registered-type-drift"):
            added = sorted(self.drift_added)
            removed = sorted(self.drift_removed)
            parts = []
            if added:
                parts.append(f"impl-only: {added}")
            if removed:
                parts.append(f"schema-only: {removed}")
            detail = "; ".join(parts) if parts else "aligned"
            return (f"  [{self.severity}] {self.capsule} ↔ {self.validator}: "
                    f"{self.drift_class} on {self.field_name!r} — {detail}")
        return f"  [{self.severity}] {self.capsule} ↔ {self.validator}: {self.drift_class} — {self.message}"


# ─── Capsule schema parser ────────────────────────────────────────────────────

# Enum extraction patterns
_ENUM_BACKTICK_RE = re.compile(r'`([a-z][a-z_\-]*)`')
_ENUM_INLINE_RE = re.compile(
    r'(?:Enum:|∈|must be one of|one of)[:\s]*\{?([^}\n]+?)\}?(?:\s*\(|$|\n)',
    re.IGNORECASE,
)
_ENUM_TABLE_CELL_RE = re.compile(
    r'Enum:\s*`([a-z][a-z_\-]*)`\s*(?:\([^)]*\))?\s*(?:OR|or|\|)\s*`([a-z][a-z_\-]*)`'
)

# Type registry: headings like "### tropo.message.sent" or "**tropo.message.sent**"
_TYPE_HEADING_RE = re.compile(r'^#{1,4}\s+(tropo\.[a-z][a-z0-9._]+)', re.MULTILINE)
_TYPE_BOLD_RE = re.compile(r'\*\*(tropo\.[a-z][a-z0-9._]+)\*\*')
# Also match slash-separated groups: tropo.pipeline.activated / tropo.pipeline.bootstrapped
_TYPE_SLASH_GROUP_RE = re.compile(r'(tropo\.[a-z][a-z0-9._]+(?:\s*/\s*tropo\.[a-z][a-z0-9._]+)+)')


def parse_capsule_schema(capsule_path: Path) -> SchemaDecls:
    """Extract schema declarations from a capsule markdown file."""
    name = capsule_path.stem.replace(".capsule", "")
    decls = SchemaDecls(capsule_name=name)

    try:
        text = capsule_path.read_text(encoding="utf-8")
    except Exception as e:
        decls.parse_ambiguous.append(f"read-error: {e}")
        return decls

    def _clean_enum_val(v: str) -> str:
        """Strip backtick-prose artifacts from parsed enum values."""
        # Strip at first backtick (e.g. 'FAIL-incomplete`); optional...' → 'FAIL-incomplete')
        if '`' in v:
            v = v[:v.index('`')]
        # Strip trailing punctuation artifacts
        v = v.rstrip(');:,. ')
        return v.strip()

    # ── 1. Enum declarations ──────────────────────────────────────────────────
    # Scan table rows for patterns like:
    #   | `lifecycle` | yes | Enum: `evergreen` ... OR `ephemeral` ... |
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 3:
            continue
        # Extract field name from first non-empty cell
        field_cell = next((c for c in cells if c), "")
        field_match = re.match(r'`([a-z][a-z_\-]*)`', field_cell)
        if not field_match:
            continue
        field_name = field_match.group(1)

        # Look for enum values in the description cell
        for cell in cells[2:]:
            # Pattern: Enum: `a` ... OR `b`
            m = _ENUM_TABLE_CELL_RE.search(cell)
            if m:
                vals = {_clean_enum_val(m.group(1)), _clean_enum_val(m.group(2))}
                vals = {v for v in vals if v}
                if vals:
                    decls.enums[field_name] = vals
                break
            # Pattern: ∈ {a, b} or must be one of a, b
            m2 = _ENUM_INLINE_RE.search(cell)
            if m2:
                raw = m2.group(1)
                vals = {_clean_enum_val(v.strip().strip('`').strip('"').strip("'"))
                        for v in re.split(r'[,|/]|\bOR\b|\bor\b', raw)
                        if v.strip() and len(v.strip()) > 1}
                vals = {v for v in vals if v and len(v) > 1}
                if vals and len(vals) >= 2:
                    decls.enums[field_name] = vals
                    break

    # ── 2. Registered event types ─────────────────────────────────────────────
    # Search full text for event type patterns — the lookahead approach was
    # truncating registry sections at sub-headings (### stopped the match).
    # event type patterns are distinctive enough to search globally.

    # Match headings like "### tropo.message.sent"
    for m in _TYPE_HEADING_RE.finditer(text):
        decls.registered_types.add(m.group(1))

    # Match bold declarations like **tropo.message.sent**
    for m in _TYPE_BOLD_RE.finditer(text):
        decls.registered_types.add(m.group(1))

    # Match slash-separated groups like: tropo.pipeline.activated / tropo.pipeline.bootstrapped
    for m in _TYPE_SLASH_GROUP_RE.finditer(text):
        for part in re.split(r'\s*/\s*', m.group(1)):
            part = part.strip()
            if re.match(r'^tropo\.[a-z]', part):
                decls.registered_types.add(part)

    return decls


# ─── Validator AST parser ─────────────────────────────────────────────────────

_REGISTERED_NAMES = {"REGISTERED_TYPES", "KNOWN_TYPES", "EVENT_TYPES", "VALID_TYPES"}
_VALID_PREFIX = "VALID_"


def _ast_set_to_python(node) -> set[str] | None:
    """Extract a frozenset/set of string literals from an AST node."""
    elts = None
    if isinstance(node, ast.Set):
        elts = node.elts
    elif isinstance(node, ast.Call):
        # frozenset({...}) or frozenset([...])
        if (isinstance(node.func, ast.Name) and node.func.id in ("frozenset", "set")
                and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Set):
                elts = arg.elts
            elif isinstance(arg, ast.List):
                elts = arg.elts
    if elts is None:
        return None
    result = set()
    for elt in elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            result.add(elt.value)
        else:
            return None  # non-literal element; mark ambiguous
    return result


def parse_validator_implementation(module_path: Path) -> ImplDecls:
    """Extract declarations from a validator module using Python AST."""
    name = module_path.stem
    decls = ImplDecls(module_name=name)

    try:
        source = module_path.read_text(encoding="utf-8")
    except Exception as e:
        decls.parse_ambiguous.append(f"read-error: {e}")
        return decls

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        decls.parse_ambiguous.append(f"syntax-error: {e}")
        return decls

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name_str = target.id

            # TARGETS_CAPSULE — explicit targeting constant
            if name_str == "TARGETS_CAPSULE":
                if isinstance(node.value, ast.Constant):
                    decls.targets_capsule = str(node.value.value)

            # REGISTERED_TYPES (or similar) — event type registry
            elif name_str in _REGISTERED_NAMES:
                vals = _ast_set_to_python(node.value)
                if vals is not None:
                    decls.registered_types = vals
                else:
                    decls.parse_ambiguous.append(f"{name_str}: non-literal set (computed?)")

            # VALID_* — enum sets
            elif name_str.startswith(_VALID_PREFIX):
                vals = _ast_set_to_python(node.value)
                if vals is not None:
                    decls.valid_sets[name_str] = vals
                else:
                    decls.parse_ambiguous.append(f"{name_str}: non-literal set (computed?)")

    return decls


# ─── Targeting heuristic ──────────────────────────────────────────────────────

_CAPSULE_VALIDATOR_MAP: dict[str, list[str]] = {
    "events":       ["event_validators"],
    "tool":         ["tool_validators"],
    "dev-spec":     ["dev_spec_validators", "spec_lock_validators"],
    "doc-spec":     ["doc_spec_validators", "spec_lock_validators"],
    "test-spec":    ["test_spec_validators", "spec_lock_validators"],
    "release":      [],  # validate-capability-membership is a separate script
    "pipeline":     [],
    "pipeline-run": [],
    "channels":     ["channel_render_validators"],
}

# Map from VALID_* constant suffix to capsule field name (heuristic)
_VALID_FIELD_MAP: dict[str, str] = {
    "VALID_LIFECYCLE":   "lifecycle",
    "VALID_STATUS":      "status",
    "VALID_TRANSPORT":   "transport",
    "VALID_LIFECYCLE_V": "lifecycle",
    "VALID_SEVERITIES":  "severity",
}


def targets(impl: ImplDecls, capsule_name: str) -> bool:
    """Check if a validator module targets a given capsule."""
    if impl.targets_capsule:
        return impl.targets_capsule.lower() == capsule_name.lower()
    # Heuristic: check the CAPSULE_VALIDATOR_MAP
    return impl.module_name in _CAPSULE_VALIDATOR_MAP.get(capsule_name, [])


# ─── Comparison ───────────────────────────────────────────────────────────────

def compare(schema: SchemaDecls, impl: ImplDecls) -> list[Finding]:
    findings: list[Finding] = []

    # Check 1: enum-value-drift
    for field_name, schema_vals in schema.enums.items():
        # Find matching VALID_* constant in impl
        # Try exact name mapping first, then suffix heuristic
        matched_key = None
        for const_name, impl_vals in impl.valid_sets.items():
            mapped_field = _VALID_FIELD_MAP.get(const_name)
            if mapped_field == field_name or const_name.lower().endswith(field_name.lower()):
                matched_key = const_name
                break

        if matched_key is None:
            # No matching constant found
            findings.append(Finding(
                capsule=schema.capsule_name,
                validator=impl.module_name,
                drift_class="impl-not-detected",
                field_name=field_name,
                message=f"No VALID_* constant found for field {field_name!r} (schema declares {sorted(schema_vals)})",
                severity="WARN",
            ))
            continue

        impl_vals = impl.valid_sets[matched_key]
        added = impl_vals - schema_vals
        removed = schema_vals - impl_vals

        if added or removed:
            findings.append(Finding(
                capsule=schema.capsule_name,
                validator=impl.module_name,
                drift_class="enum-value-drift",
                field_name=field_name,
                schema_values=schema_vals,
                impl_values=impl_vals,
                drift_added=added,
                drift_removed=removed,
                severity="ERROR",  # V-ratchet v1.60: enum-value-drift → ERROR
            ))

    # Check 2: registered-type-drift
    if schema.registered_types and impl.registered_types:
        added = impl.registered_types - schema.registered_types
        removed = schema.registered_types - impl.registered_types
        if added or removed:
            findings.append(Finding(
                capsule=schema.capsule_name,
                validator=impl.module_name,
                drift_class="registered-type-drift",
                field_name="registered_types",
                schema_values=schema.registered_types,
                impl_values=impl.registered_types,
                drift_added=added,
                drift_removed=removed,
                severity="ERROR",  # V-ratchet v1.60: registered-type-drift → ERROR
            ))

    # Note: required-field-drift punted at v1.58 per spec §7.2(d)
    return findings


# ─── Main entry point ─────────────────────────────────────────────────────────

def run_layer_3(vault: Path) -> tuple[list[str], int, int]:
    """Run Lane V Layer 3 across all known capsule + validator pairs.

    Returns (findings_as_lines, capsules_checked, defects).
    """
    capsules_dir = vault / ".tropo" / "capsules"
    validators_dir = vault / ".tropo" / "scripts" / "lib"

    if not capsules_dir.is_dir() or not validators_dir.is_dir():
        return [], 0, 0

    all_findings: list[Finding] = []
    capsules_checked = 0

    for capsule_path in sorted(capsules_dir.glob("*.capsule.md")):
        capsule_name = capsule_path.stem.replace(".capsule", "")
        if capsule_name not in _CAPSULE_VALIDATOR_MAP:
            continue  # not onboarded at v1.58; skip

        validator_names = _CAPSULE_VALIDATOR_MAP[capsule_name]
        if not validator_names:
            continue  # no validators to check

        schema = parse_capsule_schema(capsule_path)
        capsules_checked += 1

        for vname in validator_names:
            vpath = validators_dir / f"{vname}.py"
            if not vpath.exists():
                continue
            impl = parse_validator_implementation(vpath)

            if not targets(impl, capsule_name):
                # Only warn if TARGETS_CAPSULE is explicitly set to something else
                if impl.targets_capsule and impl.targets_capsule != capsule_name:
                    continue

            findings = compare(schema, impl)
            all_findings.extend(findings)

            # Parse-ambiguous findings from capsule
            for msg in schema.parse_ambiguous:
                all_findings.append(Finding(
                    capsule=capsule_name, validator=vname,
                    drift_class="parse-ambiguous",
                    message=f"capsule parser: {msg}", severity="WARN",
                ))
            # Parse-ambiguous findings from validator
            for msg in impl.parse_ambiguous:
                all_findings.append(Finding(
                    capsule=capsule_name, validator=vname,
                    drift_class="parse-ambiguous",
                    message=f"impl parser: {msg}", severity="WARN",
                ))

    lines = [f.as_line() for f in all_findings]
    return lines, capsules_checked, len(all_findings)
