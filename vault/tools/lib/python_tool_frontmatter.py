#!/usr/bin/env python3
"""One parser for Python tool frontmatter, whatever shape the fence takes.

WHY THIS FILE EXISTS. A `.py` tool carries its governed frontmatter inside the
module docstring, so the markdown splitter never sees it and every consumer
grows its own extractor. The ship-floor gate grew one shaped like this:

    re.search(r'^---\\n(.*?)\\n---\\s*$', text, re.S | re.M)

`^---` demands the opening fence start a line, which is true of

    #!/usr/bin/env python3
    \"\"\"
    ---
    uid: ...

and false of the equally common

    #!/usr/bin/env python3
    \"\"\"---
    uid: ...

where the fence shares the docstring's opening line. Tools written in the
second shape were not failing the gate — they were never reaching it. Three
shipped tools sat outside the floor check with nothing reporting their absence:
`tropo-distiller-model-edge.py`, `tropo-distiller-metered-canary.py`, and
`tropo-release-validation-gate.py`.

Anchoring to the module docstring rather than to line starts also fixes the
other half of the same defect. A file-wide regex matches a fence anywhere,
including inside a template string that renders frontmatter for some other
file — `tropo-lock-release-plan.py` has no frontmatter of its own yet contains
such a fence. The module docstring is the AST's first statement, so prose and
templates below it cannot impersonate a header.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

__all__ = [
    "module_docstring",
    "tool_frontmatter",
    "frontmatter_scalar",
    "iter_tools",
    "iter_shipped_tools",
    "shipped_tool_paths",
    "helper_imports",
    "shipped_helper_chain",
    "shipped_census",
]

# The docstring's own content, fences already removed. Leading whitespace is
# tolerated so the newline shape and the same-line shape reduce to one case.
_FRONTMATTER = re.compile(r"\A\s*---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)

# Only used when the file does not parse. Matches the first triple-quoted
# string at the top of the module, allowing a shebang, encoding line, comments,
# blank lines, and any string prefix.
_LEADING_DOCSTRING = re.compile(
    r"\A(?:\s*(?:#[^\n]*)?\n)*\s*[rRbBuUfF]{0,2}(\"\"\"|''')(.*?)\1",
    re.S,
)


def module_docstring(text: str) -> Optional[str]:
    """The module docstring's raw content, or None.

    Parses first so the answer is exact for every legal fence shape. Falls back
    to a textual scan only when the module does not parse, because a shipped
    tool with a syntax error still needs to be discovered and reported rather
    than silently dropped from the corpus.
    """
    try:
        return ast.get_docstring(ast.parse(text), clean=False)
    except SyntaxError:
        match = _LEADING_DOCSTRING.match(text)
        return match.group(2) if match else None


def tool_frontmatter(text: str) -> Optional[str]:
    """The YAML frontmatter block inside a tool's module docstring, or None."""
    doc = module_docstring(text)
    if not doc:
        return None
    match = _FRONTMATTER.match(doc)
    return match.group(1) if match else None


def frontmatter_scalar(frontmatter: str, key: str) -> Optional[str]:
    """A top-level scalar, unquoted. Nested keys are deliberately invisible."""
    match = re.search(
        r"^%s:[ \t]*(.+?)[ \t]*$" % re.escape(key), frontmatter, re.M
    )
    if not match:
        return None
    return match.group(1).strip().strip("'\"")


def iter_tools(tools_dir: Path) -> Iterator[Tuple[Path, Optional[str]]]:
    """Every top-level `.py` in `tools_dir`, with its frontmatter or None."""
    if not tools_dir.is_dir():
        return
    for path in sorted(tools_dir.glob("*.py")):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        yield path, tool_frontmatter(text)


def iter_shipped_tools(tools_dir: Path) -> Iterator[Tuple[Path, str]]:
    """Every tool declaring `extraction_scope: ship`."""
    for path, frontmatter in iter_tools(tools_dir):
        if frontmatter is None:
            continue
        if frontmatter_scalar(frontmatter, "extraction_scope") == "ship":
            yield path, frontmatter


def shipped_tool_paths(tools_dir: Path) -> List[Path]:
    """The shipped corpus as a list — the discovery half of coverage."""
    return [path for path, _ in iter_shipped_tools(tools_dir)]


def helper_imports(text: str, lib_dir: Path) -> List[Path]:
    """The `lib/` helpers one module pulls in, by either mechanism.

    Two mechanisms, because this tree uses both and a census that saw only one
    would have a hole the size of the other:

      * ``from lib.x import y`` / ``import lib.x`` — the ordinary path; and
      * ``spec_from_file_location(..., <something>/"x.py")`` — the path-load
        that `tropo-validate.py` uses deliberately to dodge the `lib`
        namespace collision.

    The second is matched on the string literal, so it is resolved by name
    against `lib_dir` rather than by following the expression. That is coarse,
    and coarse in the safe direction: a name that resolves to a real helper is
    included, and one that does not is ignored.
    """
    found: List[Path] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return found

    def take(stem: str) -> None:
        candidate = lib_dir / (stem + ".py")
        if candidate.is_file() and candidate not in found:
            found.append(candidate)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "lib":
                for alias in node.names:
                    take(alias.name)
            elif node.module.startswith("lib."):
                take(node.module.split(".", 1)[1].split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("lib."):
                    take(alias.name.split(".", 1)[1].split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.endswith(".py"):
                take(Path(node.value).stem)
    return found


def shipped_helper_chain(tools_dir: Path) -> List[Path]:
    """Every `lib/` helper reachable from a shipped tool, transitively.

    A shipped tool that imports a helper carrying a 3.10-only annotation fails
    on a 3.9 Studio at import, exactly as if the annotation were in the tool
    itself. Censusing the tools alone would therefore report a floor the
    shipped code does not actually meet.
    """
    lib_dir = Path(tools_dir) / "lib"
    if not lib_dir.is_dir():
        return []

    seen: Dict[Path, None] = {}
    frontier = list(shipped_tool_paths(tools_dir))
    while frontier:
        current = frontier.pop()
        try:
            text = current.read_text(errors="replace")
        except OSError:
            continue
        for helper in helper_imports(text, lib_dir):
            if helper not in seen:
                seen[helper] = None
                frontier.append(helper)
    return sorted(seen)


def shipped_census(tools_dir: Path) -> List[Path]:
    """Everything the ship floor must examine: the tools and their helpers."""
    return sorted(set(shipped_tool_paths(tools_dir)) | set(shipped_helper_chain(tools_dir)))
