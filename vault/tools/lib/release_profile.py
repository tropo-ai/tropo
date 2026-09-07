"""The typed release-profile loader.

Stream 1 of v1.92 (dev-spec 5b608d28), AC5 — the seam that keeps the release
machine ignorant of what product it ships. A release profile is a governed
vault entry of type `release-profile` (capsule 654f3a90, drafted by Argus
A156 under this same spec — status draft, since only Mike locks a new type):
three generic slots (build-the-artifact / verify-the-artifact /
publish-the-artifact), each naming a `release_gates` phase as its
gate_contract and a list of executor bindings in `lib.release_bindings`'s
vocabulary — the SAME vocabulary the tools declare, so a profile and a tool
cannot disagree about what "deterministic" means.

Fork the profile, not the machine. v1.92 ships exactly one profile; a second
is built when a second product needs the machine, not before.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

_TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from lib.fast_yaml import safe_load  # noqa: E402
from lib.release_bindings import (  # noqa: E402
    BindingError,
    ExecutorBinding,
    binding_from_declaration,
    collect,
)
from lib.release_gates import PHASES  # noqa: E402

__all__ = [
    "SLOTS",
    "ReleaseProfileError",
    "SlotSpec",
    "ReleaseProfile",
    "load_profile_from_frontmatter",
    "load_profile",
    "iter_release_profile_uids",
]

#: The three generic slots, closed and enum-enforced (capsule 654f3a90 §3).
#: A fourth slot would be a product concern leaking back into the machine.
SLOTS: Tuple[str, ...] = (
    "build-the-artifact",
    "verify-the-artifact",
    "publish-the-artifact",
)


class ReleaseProfileError(RuntimeError):
    """A malformed release profile. Never a release verdict."""


@dataclass(frozen=True)
class SlotSpec:
    """One of the three generic slots, populated for one product."""

    slot: str
    gate_contract: str
    steps: Tuple[ExecutorBinding, ...]


@dataclass(frozen=True)
class ReleaseProfile:
    """One product's binding of the release machine's three generic slots."""

    uid: str
    product: str
    pipeline_uid: str
    slots: Tuple[SlotSpec, ...]

    def slot_for(self, slot_name: str) -> Optional[SlotSpec]:
        for spec in self.slots:
            if spec.slot == slot_name:
                return spec
        return None

    def ordered_steps(self) -> List[ExecutorBinding]:
        """Every step, slot order first (build, verify, publish), declared
        order within a slot second — the order a runner walks."""
        out: List[ExecutorBinding] = []
        for name in SLOTS:
            spec = self.slot_for(name)
            if spec is not None:
                out.extend(spec.steps)
        return out


def _parse_frontmatter(text: str) -> Optional[Dict[str, Any]]:
    """Frontmatter as a mapping, or None. Never raises on a malformed file.

    WARN-SAFE, DELIBERATELY, and it cost a release to learn why. This called
    safe_load() bare, and iter_release_profile_uids() below runs it over EVERY
    file in the governed entry store to find the handful carrying
    `type: release-profile`. So ONE unparseable frontmatter anywhere in a
    ~5,000-file vault crashed the whole release runner with a raw
    yaml.parser.ParserError and no filename.

    That is not hypothetical. An abandon-and-relock recovery wrote an
    `abandon_reason:` whose single-quoted scalar contained a bare apostrophe —
    which terminates the scalar early — into five governed records at once. All
    five refused to parse, and the runner's `--execute` path could not enumerate
    a single profile as a result.

    Skipping silently would be worse than crashing — that is the shape this
    Studio keeps finding. So it skips AND SAYS SO, naming the file, which is
    exactly the warn-safe contract (deb77758): visible, stated in the record,
    and the work proceeds. A profile that genuinely fails to parse still cannot
    be loaded; it simply no longer takes every unrelated release with it.
    (argus-a158, 2026-08-26.)
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        parsed = safe_load(text[4:end])
    except Exception as exc:  # noqa: BLE001 — one bad file must not stop a release
        print(
            "[WARN] release-profile scan skipped a file with unparseable "
            "frontmatter: %s" % str(exc).splitlines()[0],
            file=sys.stderr,
        )
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def load_profile_from_frontmatter(
    fm: Mapping[str, Any],
    declared_leaves: Optional[Tuple[str, ...]] = None,
) -> ReleaseProfile:
    """Build a `ReleaseProfile` from already-parsed frontmatter.

    Separated from `load_profile` so a fixture profile (a dict authored in a
    test, never written to disk) drives the exact same validation path a
    real vault entry takes — the AC5 same-loader assertion.
    """
    if fm.get("type") != "release-profile":
        raise ReleaseProfileError(
            "frontmatter declares type %r; expected 'release-profile'"
            % (fm.get("type"),)
        )
    uid = fm.get("uid")
    product = fm.get("product")
    pipeline_uid = fm.get("pipeline_uid")
    if not uid:
        raise ReleaseProfileError("release profile has no uid")
    if not product or not isinstance(product, str):
        raise ReleaseProfileError("release profile %s names no product" % uid)
    if not pipeline_uid or not isinstance(pipeline_uid, str):
        raise ReleaseProfileError(
            "release profile %s names no pipeline_uid" % uid
        )

    raw_slots = fm.get("slots")
    if not isinstance(raw_slots, list):
        raise ReleaseProfileError("release profile %s has no slots list" % uid)

    seen_slot_names: Dict[str, int] = {}
    slot_specs: List[SlotSpec] = []
    all_declarations: List[Any] = []

    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            raise ReleaseProfileError(
                "release profile %s declares a non-mapping slot entry" % uid
            )
        slot_name = raw_slot.get("slot")
        gate_contract = raw_slot.get("gate_contract")
        steps = raw_slot.get("steps")

        if slot_name not in SLOTS:
            raise ReleaseProfileError(
                "release profile %s declares slot %r; expected one of %s"
                % (uid, slot_name, ", ".join(SLOTS))
            )
        seen_slot_names[slot_name] = seen_slot_names.get(slot_name, 0) + 1

        if gate_contract not in PHASES:
            raise ReleaseProfileError(
                "release profile %s slot %s declares gate_contract %r; "
                "expected one of the release_gates phases %s"
                % (uid, slot_name, gate_contract, ", ".join(PHASES))
            )

        if not isinstance(steps, list):
            raise ReleaseProfileError(
                "release profile %s slot %s has no steps list" % (uid, slot_name)
            )

        try:
            bindings = [binding_from_declaration(row) for row in steps]
        except BindingError as exc:
            raise ReleaseProfileError(
                "release profile %s slot %s: %s" % (uid, slot_name, exc)
            ) from exc

        all_declarations.extend(steps)
        slot_specs.append(
            SlotSpec(
                slot=slot_name,
                gate_contract=gate_contract,
                steps=tuple(bindings),
            )
        )

    missing = [s for s in SLOTS if s not in seen_slot_names]
    if missing:
        raise ReleaseProfileError(
            "release profile %s is missing slot(s): %s"
            % (uid, ", ".join(missing))
        )
    duplicated = [s for s, n in seen_slot_names.items() if n > 1]
    if duplicated:
        raise ReleaseProfileError(
            "release profile %s declares slot(s) more than once: %s"
            % (uid, ", ".join(duplicated))
        )

    # Set-level rules across the WHOLE profile, not per-slot: one executor
    # per step_uid, and every step_uid a live leaf when the caller supplies
    # the pipeline's declared leaves.
    try:
        collect(all_declarations, declared_leaves=declared_leaves)
    except BindingError as exc:
        raise ReleaseProfileError("release profile %s: %s" % (uid, exc)) from exc

    return ReleaseProfile(
        uid=str(uid),
        product=str(product),
        pipeline_uid=str(pipeline_uid),
        slots=tuple(slot_specs),
    )


def load_profile(
    vault_root: Path,
    uid: str,
    declared_leaves: Optional[Tuple[str, ...]] = None,
    check_product_unique: bool = True,
) -> ReleaseProfile:
    """Load a governed `type: release-profile` vault entry by uid.

    `check_product_unique` scans vault/files/ for another active/locked
    release-profile claiming the same product (capsule rule 7) — the
    forked-machine problem returning by another door.
    """
    vault_root = Path(vault_root)
    path = vault_root / "vault" / "files" / f"{uid}.md"
    if not path.is_file():  # Slug-aware (2026-09-03, metis-g118): <slug>-<uid>.md is canonical since 08-31. The bare path is tried first (u...
        _hits = [p for p in (vault_root / "vault" / "files").glob(f"*-{uid}.md") if p.name.endswith(f"-{uid}.md")]
        if len(_hits) == 1:
            path = _hits[0]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseProfileError(
            "cannot read release profile %s: %s" % (uid, exc)
        ) from exc

    fm = _parse_frontmatter(text)
    if fm is None:
        raise ReleaseProfileError(
            "release profile %s has no parseable frontmatter" % uid
        )

    profile = load_profile_from_frontmatter(fm, declared_leaves=declared_leaves)

    if check_product_unique:
        files_dir = vault_root / "vault" / "files"
        for other in sorted(files_dir.glob("*.md")):
            if other.stem == uid:
                continue
            try:
                other_fm = _parse_frontmatter(other.read_text(errors="replace"))
            except Exception:
                continue
            if not other_fm or other_fm.get("type") != "release-profile":
                continue
            if other_fm.get("status") not in ("active", "locked"):
                continue
            if other_fm.get("product") == profile.product:
                raise ReleaseProfileError(
                    "release profile %s and %s both claim product %r"
                    % (uid, other.stem, profile.product)
                )

    return profile


def iter_release_profile_uids(vault_root: Path) -> List[str]:
    """Every `type: release-profile` entry's uid under vault/files/, sorted.

    The discovery half of "a release profile is a governed vault entry ...
    discovered by uid and type like every other governed record" (capsule
    654f3a90 §Intent). A stranger should not need to already know a uid to
    find the one profile a Studio ships — this is what a caller with no
    uid in hand reads instead of guessing one.
    """
    vault_root = Path(vault_root)
    files_dir = vault_root / "vault" / "files"
    if not files_dir.is_dir():
        return []
    uids: List[str] = []
    for f in sorted(files_dir.glob("*.md")):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        if fm and fm.get("type") == "release-profile":
            uids.append(str(fm.get("uid") or f.stem))
    return uids
