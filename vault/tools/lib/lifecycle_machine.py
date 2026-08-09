"""Strict parser and normalizer for capsule lifecycle-machine declarations.

Capsule frontmatter is canonical.  This module reads it without modifying source
bytes, validates the declaration against the capsule's enforced enum and
meta-status rollup, and exposes deterministic rows for the SQLite read model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
    from yaml.constructor import ConstructorError
except ImportError:  # pragma: no cover - exercised only in dependency-broken installs
    yaml = None  # type: ignore[assignment]
    ConstructorError = ValueError  # type: ignore[assignment,misc]


VALID_DIRECTIONS = frozenset({"forward", "back"})
VALID_META_STATUS_BUCKETS = frozenset(
    {"to-do", "in-progress", "done", "standing"}
)
_VALUE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_FRONTMATTER_RE = re.compile(
    r"\A---[^\S\n]*\n(?P<frontmatter>.*?)\n---[^\S\n]*(?:\n|\Z)",
    re.DOTALL,
)


class LifecycleMachineError(ValueError):
    """A capsule lifecycle declaration is malformed or internally inconsistent."""


if yaml is not None:

    class _UniqueKeyLoader(yaml.SafeLoader):
        """Safe YAML loader that rejects duplicate metadata keys."""


    def _construct_unique_mapping(
        loader: _UniqueKeyLoader,
        node: Any,
        deep: bool = False,
    ) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate metadata key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping


    _UniqueKeyLoader.add_constructor(  # type: ignore[possibly-undefined]
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


@dataclass(frozen=True)
class LifecycleState:
    value: str
    label: str
    terminal: bool
    state_ord: int


@dataclass(frozen=True)
class LifecycleAlias:
    alias: str
    canonical_state: str


@dataclass(frozen=True)
class LifecycleMove:
    move_id: str
    from_state: str
    to_state: str
    label: str
    direction: str
    confirm: bool
    resolution: str | None
    gate: str | None
    warning: str | None
    principal_only: bool
    legacy_default: bool
    move_ord: int


@dataclass(frozen=True)
class LifecycleMachine:
    type_name: str
    field: str
    optional: bool
    states: tuple[LifecycleState, ...]
    moves: tuple[LifecycleMove, ...]
    aliases: tuple[LifecycleAlias, ...]
    capsule_path: Path

    def machine_rows(self) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            (
                self.type_name,
                self.field,
                int(self.optional),
                state.value,
                state.label,
                state.state_ord,
                int(state.terminal),
            )
            for state in self.states
        )

    def transition_rows(self) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            (
                self.type_name,
                move.move_id,
                move.from_state,
                move.to_state,
                move.move_ord,
                move.label,
                move.direction,
                int(move.confirm),
                move.resolution,
                move.gate,
                move.warning,
                int(move.principal_only),
                int(move.legacy_default),
            )
            for move in self.moves
        )

    def alias_rows(self) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            (self.type_name, alias.alias, alias.canonical_state)
            for alias in self.aliases
        )


def _fail(path: Path, message: str) -> LifecycleMachineError:
    return LifecycleMachineError(f"{path.name}: {message}")


def _frontmatter(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _fail(path, f"cannot read strict UTF-8 source: {exc}") from exc
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise _fail(path, "missing or unterminated leading frontmatter")
    return match.group("frontmatter")


def _top_level_block(
    frontmatter: str,
    key: str,
    path: Path,
    *,
    required: bool,
) -> str | None:
    lines = frontmatter.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.match(rf"^{re.escape(key)}\s*:", line)
    ]
    if not starts:
        if required:
            raise _fail(path, f"missing required {key} declaration")
        return None
    if len(starts) != 1:
        raise _fail(path, f"duplicate top-level {key} declarations")

    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            end = index
            break
    return "\n".join(lines[start:end])


def _parse_block(block: str, key: str, path: Path) -> Any:
    if yaml is None:
        raise _fail(
            path,
            f"cannot parse {key}: PyYAML is unavailable; refusing to skip validation",
        )
    try:
        parsed = yaml.load(block, Loader=_UniqueKeyLoader)
    except Exception as exc:
        raise _fail(path, f"malformed {key} YAML: {exc}") from exc
    if not isinstance(parsed, dict) or set(parsed) != {key}:
        raise _fail(path, f"{key} must be one top-level mapping entry")
    return parsed[key]


def _validate_frontmatter_yaml(frontmatter: str, path: Path) -> None:
    """Require the opted-in capsule's complete frontmatter to remain valid YAML."""
    if yaml is None:
        raise _fail(
            path,
            "cannot parse frontmatter: PyYAML is unavailable; refusing to skip validation",
        )
    try:
        parsed = yaml.safe_load(frontmatter)
    except Exception as exc:
        raise _fail(path, f"malformed capsule frontmatter YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise _fail(path, "capsule frontmatter must be a mapping")


def _require_mapping_keys(
    value: Any,
    expected: set[str],
    path: Path,
    location: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(path, f"{location} must be a mapping")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected, key=str)
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if unknown:
            detail.append(f"unknown {unknown}")
        raise _fail(path, f"{location} metadata is not closed ({'; '.join(detail)})")
    return value


def _require_string(
    value: Any,
    path: Path,
    location: str,
    *,
    identifier: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, f"{location} must be a non-empty string")
    normalized = value.strip()
    if identifier and _VALUE_RE.fullmatch(normalized) is None:
        raise _fail(
            path,
            f"{location} must match {_VALUE_RE.pattern!r}; got {normalized!r}",
        )
    return normalized


def _nullable_string(value: Any, path: Path, location: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, path, location)


def _canonical_enum(
    frontmatter: str,
    field: str,
    path: Path,
) -> tuple[tuple[str, ...], dict[str, str]]:
    block = _top_level_block(
        frontmatter,
        "enforced_enums",
        path,
        required=True,
    )
    assert block is not None
    enforced = _parse_block(block, "enforced_enums", path)
    if not isinstance(enforced, dict):
        raise _fail(path, "enforced_enums must be a mapping")
    if field not in enforced:
        raise _fail(path, f"enforced_enums has no canonical field {field!r}")

    declaration = enforced[field]
    aliases: dict[str, str] = {}
    if isinstance(declaration, list):
        canonical_raw = declaration
    elif isinstance(declaration, dict):
        unknown = set(declaration) - {"canonical", "aliases"}
        if unknown or "canonical" not in declaration:
            raise _fail(
                path,
                f"enforced_enums.{field} canonical+aliases shape is malformed "
                f"(unknown={sorted(unknown)}, canonical_present={'canonical' in declaration})",
            )
        canonical_raw = declaration["canonical"]
        aliases_raw = declaration.get("aliases", {})
        if not isinstance(aliases_raw, dict):
            raise _fail(path, f"enforced_enums.{field}.aliases must be a mapping")
        for alias, target in aliases_raw.items():
            alias_value = _require_string(
                alias,
                path,
                f"enforced_enums.{field}.aliases key",
                identifier=True,
            )
            target_value = _require_string(
                target,
                path,
                f"enforced_enums.{field}.aliases.{alias_value}",
                identifier=True,
            )
            aliases[alias_value] = target_value
    else:
        raise _fail(
            path,
            f"enforced_enums.{field} must be a list or canonical+aliases mapping",
        )

    if not isinstance(canonical_raw, list) or not canonical_raw:
        raise _fail(path, f"enforced_enums.{field} canonical states must be a non-empty list")
    canonical = tuple(
        _require_string(
            value,
            path,
            f"enforced_enums.{field}.canonical[{index}]",
            identifier=True,
        )
        for index, value in enumerate(canonical_raw)
    )
    if len(set(canonical)) != len(canonical):
        raise _fail(path, f"enforced_enums.{field} contains duplicate canonical states")
    for alias, target in aliases.items():
        if alias in canonical:
            raise _fail(path, f"enforced_enums.{field} alias {alias!r} is canonical")
        if target not in canonical:
            raise _fail(
                path,
                f"enforced_enums.{field} alias {alias!r} dangles to {target!r}",
            )
    return canonical, aliases


def _validate_rollup_totality(
    frontmatter: str,
    states: tuple[str, ...],
    path: Path,
) -> None:
    block = _top_level_block(
        frontmatter,
        "meta_status_rollup",
        path,
        required=True,
    )
    assert block is not None
    rollup = _parse_block(block, "meta_status_rollup", path)
    if not isinstance(rollup, dict):
        raise _fail(path, "meta_status_rollup must be a bucket-to-values mapping")

    seen: dict[str, str] = {}
    for bucket, values in rollup.items():
        if bucket not in VALID_META_STATUS_BUCKETS:
            raise _fail(path, f"meta_status_rollup has unknown bucket {bucket!r}")
        if not isinstance(values, list) or not values:
            raise _fail(path, f"meta_status_rollup.{bucket} must be a non-empty list")
        for index, value in enumerate(values):
            normalized = _require_string(
                value,
                path,
                f"meta_status_rollup.{bucket}[{index}]",
                identifier=True,
            ).lower()
            if normalized in seen:
                raise _fail(
                    path,
                    f"meta_status_rollup value {normalized!r} appears in both "
                    f"{seen[normalized]!r} and {bucket!r}",
                )
            seen[normalized] = bucket

    missing = [state for state in states if state not in seen]
    if missing:
        raise _fail(
            path,
            f"meta_status_rollup is not total over canonical states: missing {missing}",
        )


def parse_capsule_lifecycle_machine(path: Path) -> LifecycleMachine | None:
    """Parse one capsule declaration, returning ``None`` when it opts out."""
    frontmatter = _frontmatter(path)
    block = _top_level_block(
        frontmatter,
        "lifecycle_machine",
        path,
        required=False,
    )
    if block is None:
        return None
    _validate_frontmatter_yaml(frontmatter, path)

    declaration = _require_mapping_keys(
        _parse_block(block, "lifecycle_machine", path),
        {"field", "optional", "states", "moves"},
        path,
        "lifecycle_machine",
    )
    field = _require_string(
        declaration["field"],
        path,
        "lifecycle_machine.field",
        identifier=True,
    )
    if field != "status":
        raise _fail(
            path,
            f"lifecycle_machine.field must be the canonical 'status'; got {field!r}",
        )
    optional = declaration["optional"]
    if type(optional) is not bool:
        raise _fail(path, "lifecycle_machine.optional must be a boolean")

    states_raw = declaration["states"]
    if not isinstance(states_raw, list) or not states_raw:
        raise _fail(
            path,
            "lifecycle_machine.states must be a non-empty ordered list",
        )
    states: list[LifecycleState] = []
    state_values: list[str] = []
    for state_ord, state_raw in enumerate(states_raw):
        state = _require_mapping_keys(
            state_raw,
            {"value", "label", "terminal"},
            path,
            f"lifecycle_machine.states[{state_ord}]",
        )
        value = _require_string(
            state["value"],
            path,
            f"lifecycle_machine.states[{state_ord}].value",
            identifier=True,
        )
        label = _require_string(
            state["label"],
            path,
            f"lifecycle_machine.states[{state_ord}].label",
        )
        terminal = state["terminal"]
        if type(terminal) is not bool:
            raise _fail(
                path,
                f"lifecycle_machine.states[{state_ord}].terminal must be a boolean",
            )
        if value in state_values:
            raise _fail(path, f"duplicate lifecycle state {value!r}")
        state_values.append(value)
        states.append(LifecycleState(value, label, terminal, state_ord))

    canonical, aliases = _canonical_enum(frontmatter, field, path)
    if tuple(state_values) != canonical:
        raise _fail(
            path,
            "lifecycle_machine.states must exactly match canonical enforced enum "
            f"order {list(canonical)!r}; got {state_values!r}",
        )
    _validate_rollup_totality(frontmatter, canonical, path)

    moves_raw = declaration["moves"]
    if not isinstance(moves_raw, list) or not moves_raw:
        raise _fail(
            path,
            "lifecycle_machine.moves must be a non-empty ordered list",
        )
    moves: list[LifecycleMove] = []
    move_ids: set[str] = set()
    state_set = set(state_values)
    expected_move_keys = {
        "move_id",
        "from",
        "to",
        "label",
        "direction",
        "confirm",
        "resolution",
        "gate",
        "warning",
        "principal_only",
        "legacy_default",
    }
    for move_ord, move_raw in enumerate(moves_raw):
        move = _require_mapping_keys(
            move_raw,
            expected_move_keys,
            path,
            f"lifecycle_machine.moves[{move_ord}]",
        )
        move_id = _require_string(
            move["move_id"],
            path,
            f"lifecycle_machine.moves[{move_ord}].move_id",
            identifier=True,
        )
        if move_id in move_ids:
            raise _fail(path, f"duplicate lifecycle move_id {move_id!r}")
        move_ids.add(move_id)
        from_state = _require_string(
            move["from"],
            path,
            f"lifecycle_machine.moves[{move_ord}].from",
            identifier=True,
        )
        to_state = _require_string(
            move["to"],
            path,
            f"lifecycle_machine.moves[{move_ord}].to",
            identifier=True,
        )
        for endpoint_name, endpoint in (("from", from_state), ("to", to_state)):
            if endpoint not in state_set:
                raise _fail(
                    path,
                    f"lifecycle_machine.moves[{move_ord}].{endpoint_name} "
                    f"dangles to undeclared state {endpoint!r}",
                )
        label = _require_string(
            move["label"],
            path,
            f"lifecycle_machine.moves[{move_ord}].label",
        )
        direction = _require_string(
            move["direction"],
            path,
            f"lifecycle_machine.moves[{move_ord}].direction",
        )
        if direction not in VALID_DIRECTIONS:
            raise _fail(
                path,
                f"lifecycle_machine.moves[{move_ord}].direction must be one of "
                f"{sorted(VALID_DIRECTIONS)}; got {direction!r}",
            )
        confirm = move["confirm"]
        principal_only = move["principal_only"]
        legacy_default = move["legacy_default"]
        if type(confirm) is not bool:
            raise _fail(
                path,
                f"lifecycle_machine.moves[{move_ord}].confirm must be a boolean",
            )
        if type(principal_only) is not bool:
            raise _fail(
                path,
                f"lifecycle_machine.moves[{move_ord}].principal_only must be a boolean",
            )
        if type(legacy_default) is not bool:
            raise _fail(
                path,
                f"lifecycle_machine.moves[{move_ord}].legacy_default must be a boolean",
            )
        moves.append(
            LifecycleMove(
                move_id=move_id,
                from_state=from_state,
                to_state=to_state,
                label=label,
                direction=direction,
                confirm=confirm,
                resolution=_nullable_string(
                    move["resolution"],
                    path,
                    f"lifecycle_machine.moves[{move_ord}].resolution",
                ),
                gate=_nullable_string(
                    move["gate"],
                    path,
                    f"lifecycle_machine.moves[{move_ord}].gate",
                ),
                warning=_nullable_string(
                    move["warning"],
                    path,
                    f"lifecycle_machine.moves[{move_ord}].warning",
                ),
                principal_only=principal_only,
                legacy_default=legacy_default,
                move_ord=move_ord,
            )
        )

    target_groups: dict[tuple[str, str], list[LifecycleMove]] = {}
    for move in moves:
        target_groups.setdefault((move.from_state, move.to_state), []).append(move)
    for (from_state, to_state), candidates in target_groups.items():
        defaults = [move for move in candidates if move.legacy_default]
        if len(candidates) > 1 and len(defaults) != 1:
            raise _fail(
                path,
                f"ambiguous lifecycle target {from_state!r}->{to_state!r} must have "
                f"exactly one legacy_default; found {len(defaults)}",
            )
        if len(candidates) == 1 and defaults:
            raise _fail(
                path,
                f"unambiguous lifecycle target {from_state!r}->{to_state!r} must "
                "have legacy_default false",
            )

    type_name = path.name.removesuffix(".capsule.md")
    if type_name.startswith("tropo-"):
        type_name = type_name[len("tropo-") :]
    if not type_name:
        raise _fail(path, "cannot derive governed type from capsule filename")

    return LifecycleMachine(
        type_name=type_name,
        field=field,
        optional=optional,
        states=tuple(states),
        moves=tuple(moves),
        aliases=tuple(
            LifecycleAlias(alias, canonical_state)
            for alias, canonical_state in sorted(aliases.items())
        ),
        capsule_path=path,
    )


def load_lifecycle_machines(vault_root: Path) -> tuple[LifecycleMachine, ...]:
    """Load every opted-in capsule machine in deterministic type order."""
    capsules_dir = vault_root / "vault" / "capsules"
    if not capsules_dir.is_dir():
        return ()
    machines = [
        machine
        for path in sorted(capsules_dir.glob("*.capsule.md"))
        if (machine := parse_capsule_lifecycle_machine(path)) is not None
    ]
    machines.sort(key=lambda machine: machine.type_name)
    type_names = [machine.type_name for machine in machines]
    if len(type_names) != len(set(type_names)):
        duplicate = next(
            name for name in type_names if type_names.count(name) > 1
        )
        raise LifecycleMachineError(
            f"duplicate lifecycle_machine declaration for type {duplicate!r}"
        )
    return tuple(machines)


def normalized_rows(
    machines: tuple[LifecycleMachine, ...],
) -> tuple[
    tuple[tuple[Any, ...], ...],
    tuple[tuple[Any, ...], ...],
    tuple[tuple[Any, ...], ...],
]:
    """Return deterministic machine-state, transition, and alias row tuples."""
    machine_rows = tuple(
        row for machine in machines for row in machine.machine_rows()
    )
    transition_rows = tuple(
        row for machine in machines for row in machine.transition_rows()
    )
    alias_rows = tuple(
        row for machine in machines for row in machine.alias_rows()
    )
    return machine_rows, transition_rows, alias_rows


__all__ = [
    "LifecycleMachine",
    "LifecycleAlias",
    "LifecycleMachineError",
    "LifecycleMove",
    "LifecycleState",
    "load_lifecycle_machines",
    "normalized_rows",
    "parse_capsule_lifecycle_machine",
]
