"""Every place the build path stops, and what kind of stop it is.

Stream 1 of v1.92 (dev-spec 5b608d28), AC3.

THE PROBLEM THIS EXISTS FOR. `deb77758` has been studio law since 2026-08-09:
a refusal earns its existence by naming the irreversible harm it prevents, or
it is a warning that proceeds and records. Mike's own example in that ruling was
an inbox-hygiene check that blocked a release build. Two weeks later the build
refused on a missing plan record, an empty field, and unsettled legs — and in
every one of those cases the produced artifact would have been byte-identical.
`tropo-build-release.py` references the ruling ZERO times.
`tropo-lock-release-plan.py`, written after it, cites it three times. The lock
was priced; the build never was.

THREE DISPOSITIONS, NOT TWO. The draft of this criterion offered only "priced
refusal" or "warning", and that is not survivable: a third of the stop sites in
the build path are ImportError loader guards, argv usage errors and unreadable
input. Forcing those to name an irreversible harm produces dishonest harm text —
a crash wearing a verdict's clothes. So:

    PRICED   this refusal prevents irreversible harm, and says which.
    WARN     the thing it stops is reversible; it should record and proceed.
    MISUSE   the tool could not run. NEVER a verdict on the release.

The MISUSE/verdict distinction is not invented here. `tropo-release-preflight.py`
already codifies it in its exit contract (2 = refusal, a determinate verdict;
3 = operational error, the retryable class, "deliberately not 2"), and
`lib/release_gates.py` carries it as `ReleaseGateError — registry misuse, never
a release verdict`. This module reuses that vocabulary rather than minting a
second one, because two vocabularies for one distinction is the sibling-drift
defect this whole stream is about.

ENUMERATION IS COMPUTED, NEVER PINNED. The spec draft asserted "54 sites" and
that number is not reproducible — counting methods give 65 to 80 depending on
whether you count `raise SystemExit` separately from `sys.exit`, whether loader
guards count, and whether a bare re-raise counts. A pinned count is a second
copy of the source that goes stale on the next commit. `sites()` computes it.

AND IT PARSES, IT DOES NOT GREP. `tropo-build-release.py` embeds a subprocess
script in a raw string literal (`_GENESIS_SQLITE_SCRIPT`) that itself contains
two `raise` statements. A regex enumerator counts those and is wrong by two
before it starts. AST does not see inside string literals, which is the whole
reason this reads the tree.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "PRICED",
    "WARN",
    "MISUSE",
    "DISPOSITIONS",
    "FAIL_CLOSED_CATEGORIES",
    "DispositionError",
    "RefusalSite",
    "MARKER_RE",
    "sites",
    "undispositioned",
    "demotion_candidates",
    "verdict_blocks",
    "emits_release_verdict",
    "VERDICT_CALL",
    "VERDICT_CALLS",
    "build_path_files",
]

#: This refusal prevents irreversible harm and names it.
PRICED = "priced"

#: Reversible; it SHOULD record and proceed rather than stop the build.
#:
#: READ THE MODALITY. A site marked `warn` today still exits — the marker is a
#: finding, not a behaviour. AC3 is a declaration criterion: its acceptance
#: evidence requires each site to carry exactly one disposition, that priced
#: ones name a harm, and that misuse ones emit no verdict. It does NOT require
#: converting anything, and converting control flow inside a release tool as a
#: side effect of annotating it would fold an unrelated behaviour change into a
#: locked spec's evidence.
#:
#: So `warn` means: THIS REFUSAL HAS NOT EARNED ITS EXISTENCE. Its text says
#: why. Demoting it to an actual warning is a deliberate, separately-decided
#: change — and `demotion_candidates()` is what makes the list countable
#: instead of a thing someone remembers.
WARN = "warn"

#: The tool could not run. Never a verdict on the release.
MISUSE = "misuse"

DISPOSITIONS: Tuple[str, ...] = (PRICED, WARN, MISUSE)

#: The six earned fail-closed categories (`deb77758`, Mike-ruled 2026-08-09).
#: A priced refusal must land in ONE of these. The list is closed on purpose:
#: an open list is how "fail-closed by default" comes back through the side
#: door, one plausible-sounding seventh category at a time.
FAIL_CLOSED_CATEGORIES: Tuple[str, ...] = (
    "outward-publication-and-egress",
    "deletion-of-governed-substrate",
    "spend-beyond-ceilings",
    "the-update-covenant",
    "unreconstructable-identity-or-lineage",
    "false-success",
)


class DispositionError(RuntimeError):
    """A malformed or missing disposition marker. Never a release verdict."""


#: The marker a stop site carries, on its own line directly above the statement
#: or trailing it. Deliberately a COMMENT and not a decorator or a helper call:
#: these sites sit inside deep conditionals in a 3,900-line script, several
#: inside `except` handlers, and wrapping them in anything callable would change
#: control flow in a release tool to satisfy a test. A comment changes nothing
#: at runtime, which is the correct blast radius for an annotation.
#:
#:     # refusal: misuse — could not load the roots helper
#:     # refusal: warn — records and proceeds; the box is byte-identical either way
#:     # refusal: priced/false-success — a manifest that names bytes the box does not contain
MARKER_RE = re.compile(
    r"#\s*refusal:\s*"
    r"(?P<disposition>priced|warn|misuse)"
    r"(?:\s*/\s*(?P<category>[a-z-]+))?"
    r"\s*(?:—|--|-)\s*"
    r"(?P<text>.+?)\s*$"
)


@dataclass(frozen=True)
class RefusalSite:
    """One place the build path stops."""

    path: Path
    line: int
    shape: str
    function: str
    disposition: Optional[str] = None
    category: Optional[str] = None
    text: Optional[str] = None

    @property
    def where(self) -> str:
        return f"{self.path.name}:{self.line}"

    @property
    def dispositioned(self) -> bool:
        return self.disposition is not None

    def problems(self) -> List[str]:
        """Everything wrong with this site's marker, named plainly."""
        found: List[str] = []
        if self.disposition is None:
            found.append(
                f"{self.where} ({self.shape} in {self.function}) carries no "
                f"disposition marker"
            )
            return found
        if self.disposition not in DISPOSITIONS:
            found.append(
                f"{self.where} declares disposition {self.disposition!r}; "
                f"expected one of {', '.join(DISPOSITIONS)}"
            )
        if self.disposition == PRICED:
            if not self.category:
                found.append(
                    f"{self.where} is priced but names no fail-closed category; "
                    f"a refusal that cannot say which boundary it defends has "
                    f"not earned its existence (deb77758)"
                )
            elif self.category not in FAIL_CLOSED_CATEGORIES:
                found.append(
                    f"{self.where} names category {self.category!r}, which is "
                    f"not one of the six earned categories. The list is closed: "
                    f"{', '.join(FAIL_CLOSED_CATEGORIES)}"
                )
            if not (self.text and len(self.text.split()) >= 5):
                found.append(
                    f"{self.where} is priced but names no irreversible harm. "
                    f"One sentence saying what becomes true and cannot be "
                    f"undone, or it is a warning (deb77758)"
                )
        if self.disposition == MISUSE and self.category:
            found.append(
                f"{self.where} is misuse but names a fail-closed category. "
                f"Misuse is not a verdict on the release, so it defends no "
                f"release boundary"
            )
        return found


def _enclosing_functions(tree: ast.Module) -> Dict[int, str]:
    """line -> innermost enclosing function name, for readable site reports.

    Spans are collected first and applied widest-first, so a nested def
    overwrites its parent's claim on the lines it covers and the innermost
    function wins. Ordering by span width rather than by start line is what
    makes that true for a nested def that starts late in a long parent.
    """
    spans: List[Tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            spans.append((node.lineno, end, node.name))

    owner: Dict[int, str] = {}
    for start, end, name in sorted(spans, key=lambda s: s[1] - s[0], reverse=True):
        for line in range(start, end + 1):
            owner[line] = name
    return owner


def _shape(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Raise):
        exc = node.exc
        if exc is None:
            return "raise (bare re-raise)"
        if isinstance(exc, ast.Call):
            func = exc.func
            if isinstance(func, ast.Name):
                return f"raise {func.id}"
            if isinstance(func, ast.Attribute):
                return f"raise {func.attr}"
        if isinstance(exc, ast.Name):
            return f"raise {exc.id}"
        return "raise"
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "exit"
            and isinstance(func.value, ast.Name)
            and func.value.id == "sys"
        ):
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Constant):
                return f"sys.exit({arg.value!r})"
            return "sys.exit(...)"
    return None


def _marker_for(line: int, lines: Sequence[str]) -> Optional[re.Match]:
    """The marker trailing this line, or on the comment lines above it.

    Walks upward through contiguous comment lines so a marker may sit above a
    multi-line call rather than being forced onto a 100-column statement.
    """
    if line - 1 < len(lines):
        trailing = MARKER_RE.search(lines[line - 1])
        if trailing:
            return trailing
    idx = line - 2
    while idx >= 0:
        stripped = lines[idx].strip()
        if not stripped:
            idx -= 1
            continue
        if not stripped.startswith("#"):
            return None
        found = MARKER_RE.search(lines[idx])
        if found:
            return found
        idx -= 1
    return None


def sites(path: Path) -> List[RefusalSite]:
    """Every stop site in one file, with whatever disposition it declares."""
    path = Path(path)
    source = path.read_text(errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise DispositionError(f"{path.name} does not parse: {exc}") from exc

    lines = source.splitlines()
    owners = _enclosing_functions(tree)
    found: List[RefusalSite] = []
    seen: set = set()

    for node in ast.walk(tree):
        shape = _shape(node)
        if shape is None:
            continue
        line = node.lineno
        if (line, shape) in seen:
            continue
        seen.add((line, shape))
        marker = _marker_for(line, lines)
        found.append(
            RefusalSite(
                path=path,
                line=line,
                shape=shape,
                function=owners.get(line, "<module>"),
                disposition=marker.group("disposition") if marker else None,
                category=marker.group("category") if marker else None,
                text=marker.group("text").strip() if marker else None,
            )
        )
    return sorted(found, key=lambda s: (s.line, s.shape))


def undispositioned(path: Path) -> List[RefusalSite]:
    """The sites still carrying no marker. The honest progress report.

    Deliberately NOT an exception. A module that refuses to load an
    incompletely-annotated file cannot be used to report how incomplete it is —
    the same reasoning that keeps `release_bindings.collect()` from requiring
    total leaf coverage.
    """
    return [s for s in sites(path) if not s.dispositioned]


#: EVERY call that records a determinate verdict ON THE RELEASE into provenance
#: or telemetry. A misuse site must never reach one: "I could not run" recorded
#: as "the release was refused" is a false record of a decision nobody made, and
#: it is the one thing the preflight exit contract exists to keep apart
#: (2 = verdict, 3 = operational, "deliberately not 2").
#:
#: THIS WAS ONE NAME AND THE REACH WAS 2 SITES. An independent adversarial pass
#: called the assertions over it near-vacuous, and it was right: a detector
#: knowing a single wrapper in a 4,221-line tool cannot say much about whether
#: crashes masquerade as verdicts. Measured across the whole build path, the
#: telemetry primitive is ALSO called directly — `tropo-release.py:433` reaches
#: `telemetry.record_refused` with harm_class irreversible-write, and the
#: single-name detector could not see it.
#:
#: `record_failed` is deliberately NOT here. It means "execution began and did
#: not complete", which is exactly what a misuse site should record.
VERDICT_CALLS = ("_record_build_refusal", "record_refused")

#: Retained: the original single name, still the build tool's own wrapper.
VERDICT_CALL = "_record_build_refusal"


def verdict_blocks(path: Path) -> List[Tuple[str, int, int]]:
    """(start, end) line spans of statement blocks that record a verdict.

    A block is the body a statement lives in — the arm of an `if`, a `try`, a
    loop, or a function. Co-occurrence in the same block is the test: a
    `_record_build_refusal` two lines above a `sys.exit` is the same decision,
    while one in a different branch is a different decision entirely.
    """
    path = Path(path)
    tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
    spans: List[Tuple[str, int, int]] = []

    def scan(body: List[ast.stmt]) -> None:
        """Only DIRECT statements of this block count.

        Walking each statement's subtree was the first version and it was
        useless: `main` contains a verdict call somewhere, so the whole of
        `main` read as a recording block, and so did the module body — every
        site in the file came back positive. The question is not "does a
        verdict get recorded anywhere under here" but "is this stop site part
        of the same decision", and that means the call must be a direct
        statement of the same block.
        """
        if not body:
            return
        def _is_verdict_call(stmt: ast.stmt) -> bool:
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
                return False
            func = stmt.value.func
            # Both shapes: a bare wrapper `_record_build_refusal(...)` and the
            # primitive reached through its module, `telemetry.record_refused(...)`.
            if isinstance(func, ast.Name):
                return func.id in VERDICT_CALLS
            if isinstance(func, ast.Attribute):
                return func.attr in VERDICT_CALLS
            return False

        records = any(_is_verdict_call(stmt) for stmt in body)
        if records:
            start = body[0].lineno
            end = max(
                getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno
                for stmt in body
            )
            spans.append((str(path), start, end))

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            value = getattr(node, field, None)
            if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                scan(value)
        for handler in getattr(node, "handlers", []) or []:
            scan(handler.body)
    return spans


def emits_release_verdict(
    site: RefusalSite, spans: Sequence[Tuple[str, int, int]]
) -> bool:
    """Does this stop site sit in a block that records a release verdict?

    SPANS CARRY THEIR FILE, AND THE MATCH REQUIRES IT. They did not, and once
    the build path widened from one module to four the caller pooled spans
    across all of them — so a line number in `release_package.py` could fall
    inside a span from `tropo-release.py` and be reported as emitting a verdict
    it has no code path to. Measured: `release_package.py:441` sits inside
    `tropo-release.py`'s (424, 453) and produced a fabricated finding, in a file
    that records no verdicts at all.

    That is worse than the under-reach this detector was already criticised
    for. A check that misses something leaves a gap; a check that INVENTS a
    finding, naming a real file and a real line, spends the reader's trust on a
    defect that does not exist — and the next true finding is the one they skip.

    Uses the TIGHTEST enclosing block within the site's own file: a whole
    function body is a block, so without that rule any site inside a function
    recording a verdict anywhere would read as emitting one.
    """
    here = str(site.path)
    containing = [(a, b) for f, a, b in spans
                  if f == here and a <= site.line <= b]
    if not containing:
        return False
    tightest = min(containing, key=lambda s: s[1] - s[0])
    return tightest[0] <= site.line <= tightest[1]


def demotion_candidates(path: Path) -> List[RefusalSite]:
    """Sites that stop the build without having earned it.

    The actionable output of AC3. Every one of these is a place the studio
    currently refuses over something reversible — Mike's own example in
    `deb77758` was an inbox-hygiene check that blocked a release build. They
    are not converted here; they are made countable, so that demoting them is a
    decision someone takes rather than a thing nobody can see.
    """
    return [s for s in sites(path) if s.disposition == WARN]


#: The modules the build actually executes. AC3 says "every refusal site in the
#: build path", and the first version returned ONE file on the argument that the
#: criterion's committed test target names the build tool. An independent
#: adversarial pass measured what that definition excluded: 40 stop sites, in
#: modules the build calls directly.
#:
#: `release_package.PackageRefusal` is raised FROM `tropo-build-release.py` —
#: narrowing the scope to one file meant the build could refuse through a path
#: the criterion claimed to cover and did not. And two of the three additions,
#: `tropo-release.py` and `lib/release_metrics.py`, are committed substrate
#: targets of this very spec: they were declared in scope by the spec and out of
#: scope by the code checking it.
#:
#: The publish path stays out. It has its own exit contract and its own
#: criterion, and grading two tools against one rule is a different defect.
BUILD_PATH_RELATIVE = (
    "vault/tools/tropo-build-release.py",
    "vault/tools/lib/release_package.py",
)
#: tropo-release.py and lib/release_metrics.py were REMOVED from this tuple on
#: 2026-08-25 (Mike-approved, Metis G112 release-owner ruling). The build does
#: not execute either of them — measured, not assumed: `tropo-build-release.py`
#: contains ZERO references to either module, and imports neither. They are the
#: FIRE path, which is a different boundary with a different owner.
#:
#: They were here because, in this module's own words, "they were declared in
#: scope by the spec and out of scope by the code checking it" — and the
#: docstring below still called this "every module the build executes", which
#: was not true of half the tuple. The cost was not cosmetic: 41 of the 120 stop
#: sites this module reported for "the build path" live in modules the build
#: never runs, so every count of the build's failure surface was inflated by a
#: third, and the 16 demotion candidates were being read against a denominator
#: that included another boundary's refusals.
#:
#: The fire path still needs its refusals dispositioned. It needs them counted
#: as the FIRE path, under its own name, which is a v1.93 item — not silently
#: folded into the build's number.


def build_path_files(studio_root: Path) -> List[Path]:
    """The build path AC3 governs — every module the build actually executes.

    "Actually" is load-bearing: this said "every module the build executes"
    while naming two the build has never imported. Corrected 2026-08-25.
    """
    root = Path(studio_root)
    found = []
    for relative in BUILD_PATH_RELATIVE:
        path = root / relative
        if not path.exists():
            raise DispositionError(f"build-path module missing: {path}")
        found.append(path)
    return found
