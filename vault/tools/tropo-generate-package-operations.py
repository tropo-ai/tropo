#!/usr/bin/env python3
"""
---
uid: 7e41c0d8
title: generate-package-operations — Tool
name: generate-package-operations
type: tool
status: active
owner: talos
domain: Derive an update package's manifest `operations:` block from ground truth — the package's own files/ tree diffed against the previously shipped surface — instead of authoring 573 entries by hand.
transport: cli
implementation_kind: python-script
cli_command: python3 vault/tools/tropo-generate-package-operations.py --package updates/tropo-update-vX.Y.Z --baseline <prior shipped tree> [--write]
script_path: vault/tools/tropo-generate-package-operations.py
destructive: false
audit_required: false
writes_scope:
- updates/tropo-update-*/manifest.yaml
governance_category: lifecycle
created: 2026-08-09
created_by: talos-t40
---

Generate the `operations:` block of an update package manifest FROM GROUND TRUTH.

WHY THIS EXISTS. v1.86.0's manifest was hand-authored and shipped with the
narrative but **no operations at all** — the apply engine would have had nothing
to do. It was caught by the customer's own Po at her Step-1a halt, not by us and
not by a gate. metis-g105's retrospective entry is unsparing about it: "my
manifest defect; the customer's Po caught it". Then 573 operations were written
by hand under time pressure on release night.

Both halves of that are avoidable. `add` versus `replace` is not a judgement
call — it is a fact about whether the path exists in the surface the customer is
coming from. So it is computed here, from two trees, and the human writes the
reasons rather than the inventory.

THE REFUSALS. Three, and each one is a mistake this studio has actually made:

  1. **An empty operations list is refused.** That is the v1.86.0 defect exactly.
     A package that describes itself and does nothing must not be expressible.
  2. **Per-studio STATE is refused, not silently dropped.** The exclusion rule
     lives in lib/package_state_exclusions.py and is shared with the box build,
     so a file cannot be state in one path and OS in the other. Excluded files
     are LISTED with their reason, because a packager silently omitting files is
     how 24 of our flags reached a customer.
  3. **A missing baseline is refused rather than guessed.** Assuming everything
     is a `replace` would be wrong for exactly the new files a release adds, and
     a wrong `replace` on a path the customer does not have is how v1.85.0 broke
     a real studio as a hand-curated delta cut from the wrong base.

WHAT IT DOES NOT DO. It does not write the `reason:` prose — those are a human's
statement of intent and generating them would produce 573 identical sentences
that mean nothing. It emits a reason DERIVED from the file's category, which the
author is expected to sharpen.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "tropo_package_state_exclusions_cli",
    TOOLS_DIR / "lib" / "package_state_exclusions.py",
)
if _spec is None or _spec.loader is None:
    raise SystemExit("package_state_exclusions helper could not be loaded")
psx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(psx)

BEGIN_MARKER = "operations:"


class PackagingRefusal(RuntimeError):
    """A refusal names the mistake it is preventing, never just 'invalid input'."""


def _relative_files(tree: Path) -> set[str]:
    return {
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if p.is_file()
    }


def _category_reason(relpath: str, verb: str) -> str:
    if relpath.startswith(".tropo/"):
        surface = "kernel surface (category b)"
    elif relpath.startswith("vault/"):
        surface = "governed OS surface (category a)"
    else:
        surface = "manifest-listed root doc (category d)"
    return (
        f"{verb} {surface}: taken verbatim from the walked, in-box-verified "
        f"release box. SHARPEN THIS REASON — it was derived, not authored."
    )


#: How much smaller a baseline may be than the package before it stops being
#: plausible as the full prior surface. Deliberately loose: a release CAN add a
#: lot, and a guard that fires on healthy releases is one people pass a flag to
#: silence by reflex.
BASELINE_PLAUSIBILITY_RATIO = 4


def plan_operations(
    package_files: Path,
    baseline: Path,
    *,
    allow_partial_baseline: bool = False,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Return (operations, excluded) — the inventory, computed rather than typed."""
    if not package_files.is_dir():
        raise PackagingRefusal(
            f"no files/ tree at {package_files}. A package with no payload cannot "
            "be described; this refuses rather than emitting an empty plan."
        )
    if not baseline.is_dir():
        raise PackagingRefusal(
            f"no baseline tree at {baseline}. add-vs-replace is a FACT about the "
            "surface the customer is coming from, and guessing it is how v1.85.0 "
            "broke a real studio as a delta cut from the wrong base. Point "
            "--baseline at the previously shipped tree."
        )

    prior = _relative_files(baseline)
    payload = _relative_files(package_files)

    # A baseline must be the full PRIOR SHIPPED SURFACE, not a previous delta
    # package. Point it at a delta and almost everything reads as `add`, which
    # is the wrong answer in the most dangerous direction: the apply then treats
    # existing customer paths as new. This is the shape that broke a real
    # customer at v1.85.0 — "a hand-curated delta cut from the wrong base" — and
    # the tool can only see it as a ratio, so it says so and stops.
    if (not allow_partial_baseline) and prior and \
            len(prior) * BASELINE_PLAUSIBILITY_RATIO < len(payload):
        raise PackagingRefusal(
            f"the baseline has {len(prior)} file(s) against the package's "
            f"{len(payload)}, so it looks like a previous DELTA package rather "
            "than the full prior shipped surface. Everything absent from it "
            "would be planned as `add`, which is the v1.85.0 failure exactly. "
            "Point --baseline at the previously shipped BOX, or pass "
            "--allow-partial-baseline if you have genuinely verified this is "
            "the surface the customer is coming from."
        )

    operations: list[dict] = []
    excluded: list[tuple[str, str]] = []

    for relpath in sorted(_relative_files(package_files)):
        if psx.is_studio_state(relpath):
            excluded.append((relpath, psx.why_excluded(relpath)))
            continue
        verb = "replace" if relpath in prior else "add"
        operations.append(
            {
                "type": verb,
                "path": relpath,
                "source": f"files/{relpath}",
                "reason": _category_reason(relpath, verb),
            }
        )

    if not operations:
        raise PackagingRefusal(
            "the plan is EMPTY. This is the v1.86.0 defect verbatim — a manifest "
            "that carried the narrative and no operations, caught by the "
            "customer's Po rather than by us. A package that describes itself "
            "and does nothing must not be expressible."
        )
    return operations, excluded


def render_yaml(operations: list[dict]) -> str:
    """Emit the block with properly ESCAPED scalars.

    Values go through `json.dumps` rather than being wrapped in quotes by hand.
    JSON strings are valid YAML double-quoted scalars, so this costs nothing and
    removes a whole class: the hand-quoted first version produced
    `path: "vault/files/quote"and — dash.md"`, which is a parse error, and the
    round-trip test caught it immediately. Paths carrying quotes are rare today
    and stop being rare the moment readable governed filenames land.
    """
    lines = [BEGIN_MARKER]
    for op in operations:
        lines.append(f"  - type: {json.dumps(op['type'])}")
        lines.append(f"    path: {json.dumps(op['path'], ensure_ascii=False)}")
        lines.append(f"    source: {json.dumps(op['source'], ensure_ascii=False)}")
        lines.append(f"    reason: {json.dumps(op['reason'], ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive an update package's operations: block from ground truth."
    )
    parser.add_argument("--package", required=True,
                        help="the update package directory (containing files/)")
    parser.add_argument("--baseline", required=True,
                        help="the previously shipped tree the customer is coming from")
    parser.add_argument("--allow-partial-baseline", action="store_true",
                        help="the baseline is genuinely the surface the customer "
                             "is coming from despite being much smaller")
    parser.add_argument("--write", action="store_true",
                        help="replace the operations: block in the package manifest "
                             "(default is to print the block for review)")
    args = parser.parse_args()

    package = Path(args.package).resolve()
    try:
        operations, excluded = plan_operations(
            package / "files",
            Path(args.baseline).resolve(),
            allow_partial_baseline=args.allow_partial_baseline,
        )
    except PackagingRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    adds = sum(1 for op in operations if op["type"] == "add")
    print(f"{len(operations)} operation(s): {adds} add + {len(operations) - adds} replace",
          file=sys.stderr)
    if excluded:
        # Listed, never silent. 24 of our flags reached a customer because a
        # packager omitted files without saying so.
        print(f"\n{len(excluded)} file(s) EXCLUDED as per-studio state:", file=sys.stderr)
        for relpath, reason in excluded:
            print(f"  - {relpath}\n      {reason}", file=sys.stderr)

    block = render_yaml(operations)
    if not args.write:
        print(block)
        return 0

    manifest = package / "manifest.yaml"
    if not manifest.is_file():
        print(f"REFUSED: no manifest.yaml at {manifest}", file=sys.stderr)
        return 2
    text = manifest.read_text(encoding="utf-8")
    marker = text.find("\n" + BEGIN_MARKER)
    if marker < 0:
        print(f"REFUSED: no `{BEGIN_MARKER}` block found in {manifest.name}; this "
              "tool replaces an existing block rather than guessing where one goes.",
              file=sys.stderr)
        return 2
    manifest.write_text(text[: marker + 1] + block, encoding="utf-8")
    print(f"Wrote {len(operations)} operation(s) into {manifest.name}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
