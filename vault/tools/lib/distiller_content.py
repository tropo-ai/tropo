"""Section-first, exact-span content loading from the bound composed index."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional


DEFAULT_MAX_CHUNK_BYTES = 8192


class ContentErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BODY_NOT_FOUND = "BODY_NOT_FOUND"
    INDEX_UNAVAILABLE = "INDEX_UNAVAILABLE"


class ContentError(Exception):
    def __init__(
        self, code: ContentErrorCode, message: str, *, source_uid: Optional[str] = None
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.source_uid = source_uid


@dataclass(frozen=True)
class HeadingPart:
    level: int
    text: str
    occurrence: int


@dataclass(frozen=True)
class SpanAnchor:
    """Duplicate-safe heading path plus a section-local paragraph range."""

    heading_path: tuple[HeadingPart, ...]
    paragraph_start: int
    paragraph_end: int
    whole_entry: bool = False

    def canonical(self) -> str:
        path = "/".join(
            f"h{part.level}:{part.text}#{part.occurrence}"
            for part in self.heading_path
        )
        prefix = "entry" if self.whole_entry else (path or "root")
        return f"{prefix}:p{self.paragraph_start}-p{self.paragraph_end}"


@dataclass(frozen=True)
class ContentSpan:
    source_uid: str
    span_anchor: SpanAnchor
    text: str


@dataclass(frozen=True)
class _Section:
    start: int
    end: int
    heading_path: tuple[HeadingPart, ...]
    heading_prefix_bytes: int


_ATX = re.compile(
    r"^[ \t]{0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+[ \t]*)?(?:\r?\n)?$"
)
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _line_offsets(text: str) -> list[tuple[int, int, str]]:
    lines = []
    offset = 0
    for line in text.splitlines(keepends=True):
        end = offset + len(line)
        lines.append((offset, end, line))
        offset = end
    if offset < len(text):
        lines.append((offset, len(text), text[offset:]))
    return lines


def _fence_token(line: str) -> Optional[str]:
    match = _FENCE_OPEN.match(line)
    return match.group(1) if match else None


def _closes_fence(line: str, token: str) -> bool:
    stripped = line.rstrip("\r\n")
    pattern = rf"^[ \t]{{0,3}}{re.escape(token[0])}{{{len(token)},}}[ \t]*$"
    return re.match(pattern, stripped) is not None


def _sections(text: str) -> tuple[_Section, ...]:
    lines = _line_offsets(text)
    if not lines:
        return (_Section(0, 0, (), 0),)

    boundaries: list[tuple[int, tuple[HeadingPart, ...], int]] = [(0, (), 0)]
    stack: list[HeadingPart] = []
    occurrences: dict[tuple, int] = {}
    fence: Optional[str] = None

    for start, end, line in lines:
        if fence is not None:
            if _closes_fence(line, fence):
                fence = None
            continue
        opened = _fence_token(line)
        if opened is not None:
            fence = opened
            continue
        heading = _ATX.match(line)
        if heading is None:
            continue

        level = len(heading.group(1))
        text_value = heading.group(2)
        while stack and stack[-1].level >= level:
            stack.pop()
        parent = tuple(stack)
        key = (parent, level, text_value)
        occurrence = occurrences.get(key, 0) + 1
        occurrences[key] = occurrence
        part = HeadingPart(level, text_value, occurrence)
        stack.append(part)
        boundaries.append((start, tuple(stack), end - start))

    sections = []
    for index, (start, path, prefix) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        if end > start:
            sections.append(_Section(start, end, path, prefix))
    return tuple(sections) or (_Section(0, 0, (), 0),)


def _body_atom_ranges(body: str) -> tuple[tuple[int, int], ...]:
    """Partition body bytes into exact paragraph/fenced-block atoms."""

    lines = _line_offsets(body)
    if not lines:
        return ()
    atoms: list[tuple[int, int]] = []
    cursor = 0
    index = 0
    while index < len(lines):
        start, end, line = lines[index]
        opened = _fence_token(line)
        if opened is not None:
            if body[cursor:start].strip():
                atoms.append((cursor, start))
                cursor = start
            index += 1
            fence_end = end
            while index < len(lines):
                _next_start, next_end, next_line = lines[index]
                fence_end = next_end
                index += 1
                if _closes_fence(next_line, opened):
                    break
            while index < len(lines) and not lines[index][2].strip():
                fence_end = lines[index][1]
                index += 1
            atoms.append((cursor, fence_end))
            cursor = fence_end
            continue

        if not line.strip():
            blank_end = end
            index += 1
            while index < len(lines) and not lines[index][2].strip():
                blank_end = lines[index][1]
                index += 1
            if blank_end > cursor:
                atoms.append((cursor, blank_end))
                cursor = blank_end
            continue
        index += 1

    if cursor < len(body):
        atoms.append((cursor, len(body)))
    return tuple((start, end) for start, end in atoms if end > start)


def _section_atoms(text: str, section: _Section) -> tuple[tuple[int, int], ...]:
    prefix_end = section.start + section.heading_prefix_bytes
    body = text[prefix_end : section.end]
    body_atoms = _body_atom_ranges(body)
    if not body_atoms:
        return ((section.start, section.end),) if section.end > section.start else ()

    atoms = []
    for index, (start, end) in enumerate(body_atoms):
        absolute_start = prefix_end + start
        absolute_end = prefix_end + end
        if index == 0:
            absolute_start = section.start
        atoms.append((absolute_start, absolute_end))
    return tuple(atoms)


def _byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


def chunk_body(
    source_uid: str,
    body: str,
    *,
    max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
) -> tuple[ContentSpan, ...]:
    """Return exact source spans, whole-entry first and paragraph-packed only
    when the entry is oversized."""

    if (
        isinstance(max_chunk_bytes, bool)
        or not isinstance(max_chunk_bytes, int)
        or max_chunk_bytes <= 0
    ):
        raise ContentError(
            ContentErrorCode.INVALID_ARGUMENT,
            "max_chunk_bytes must be positive",
            source_uid=source_uid,
        )
    if not isinstance(body, str):
        raise ContentError(
            ContentErrorCode.INVALID_ARGUMENT,
            "body must be text",
            source_uid=source_uid,
        )

    parsed_sections = _sections(body)
    all_atoms = tuple(
        atom
        for section in parsed_sections
        for atom in _section_atoms(body, section)
    )
    paragraph_count = max(1, len(all_atoms))
    if _byte_len(body) <= max_chunk_bytes:
        return (
            ContentSpan(
                source_uid,
                SpanAnchor((), 1, paragraph_count, whole_entry=True),
                body,
            ),
        )

    spans: list[ContentSpan] = []
    for section in parsed_sections:
        atoms = _section_atoms(body, section)
        if not atoms:
            continue
        section_text = body[section.start : section.end]
        if _byte_len(section_text) <= max_chunk_bytes:
            spans.append(
                ContentSpan(
                    source_uid,
                    SpanAnchor(section.heading_path, 1, len(atoms)),
                    section_text,
                )
            )
            continue

        group_start = 0
        group_bytes = 0
        for atom_index, (start, end) in enumerate(atoms):
            atom_bytes = _byte_len(body[start:end])
            if atom_index > group_start and group_bytes + atom_bytes > max_chunk_bytes:
                span_start = atoms[group_start][0]
                span_end = atoms[atom_index - 1][1]
                spans.append(
                    ContentSpan(
                        source_uid,
                        SpanAnchor(
                            section.heading_path,
                            group_start + 1,
                            atom_index,
                        ),
                        body[span_start:span_end],
                    )
                )
                group_start = atom_index
                group_bytes = 0
            group_bytes += atom_bytes

            # A single oversized atom is emitted whole immediately.
            if group_start == atom_index and atom_bytes > max_chunk_bytes:
                spans.append(
                    ContentSpan(
                        source_uid,
                        SpanAnchor(
                            section.heading_path,
                            atom_index + 1,
                            atom_index + 1,
                        ),
                        body[start:end],
                    )
                )
                group_start = atom_index + 1
                group_bytes = 0

        if group_start < len(atoms):
            spans.append(
                ContentSpan(
                    source_uid,
                    SpanAnchor(
                        section.heading_path,
                        group_start + 1,
                        len(atoms),
                    ),
                    body[atoms[group_start][0] : atoms[-1][1]],
                )
            )
    return tuple(spans)


class ContentLoader:
    """Body loader bound to one opaque composed-index snapshot."""

    index_as_of: str
    max_chunk_bytes: int

    def load_spans(self, source_uid: str) -> tuple[ContentSpan, ...]:
        raise NotImplementedError


class InMemoryContentLoader(ContentLoader):
    def __init__(
        self,
        bodies: Mapping[str, str],
        *,
        index_as_of: str,
        max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    ) -> None:
        self._bodies = dict(bodies)
        self.index_as_of = index_as_of
        self.max_chunk_bytes = max_chunk_bytes

    def load_spans(self, source_uid: str) -> tuple[ContentSpan, ...]:
        if source_uid not in self._bodies:
            raise ContentError(
                ContentErrorCode.BODY_NOT_FOUND,
                "indexed body not found",
                source_uid=source_uid,
            )
        return chunk_body(
            source_uid,
            self._bodies[source_uid],
            max_chunk_bytes=self.max_chunk_bytes,
        )


class SqliteContentLoader(ContentLoader):
    """Reads exact body bytes from ``entries_fts``; never reopens source files."""

    def __init__(
        self,
        index_path: "str | Path",
        *,
        index_as_of: str,
        max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    ) -> None:
        self._index_path = Path(index_path)
        self.index_as_of = index_as_of
        self.max_chunk_bytes = max_chunk_bytes
        self._conn: Optional[sqlite3.Connection] = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self._index_path.exists():
                raise ContentError(
                    ContentErrorCode.INDEX_UNAVAILABLE,
                    f"composed index not found at {self._index_path}",
                )
            self._conn = sqlite3.connect(
                f"file:{self._index_path}?mode=ro", uri=True
            )
        return self._conn

    def load_spans(self, source_uid: str) -> tuple[ContentSpan, ...]:
        try:
            row = self._connection().execute(
                "SELECT body FROM entries_fts WHERE uid=?", (source_uid,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ContentError(
                ContentErrorCode.INDEX_UNAVAILABLE,
                "indexed body read failed",
                source_uid=source_uid,
            ) from error
        if row is None:
            raise ContentError(
                ContentErrorCode.BODY_NOT_FOUND,
                "indexed body not found",
                source_uid=source_uid,
            )
        return chunk_body(
            source_uid, row[0] or "", max_chunk_bytes=self.max_chunk_bytes
        )


__all__ = [
    "DEFAULT_MAX_CHUNK_BYTES",
    "ContentErrorCode",
    "ContentError",
    "HeadingPart",
    "SpanAnchor",
    "ContentSpan",
    "chunk_body",
    "ContentLoader",
    "InMemoryContentLoader",
    "SqliteContentLoader",
]
