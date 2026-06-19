"""
publish_types.py — Shared data types for publish.py + publish_targets/*.py

Imported by publish.py (runner) and any target module that needs to construct
StageResult / PublishResult or raise PublishTargetError.

v1.49.0 S2.5 target-implementation interface contract.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class StageResult:
    success: bool
    output_paths: list[str] = field(default_factory=list)
    extracted_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PublishResult:
    success: bool
    committed: bool = False
    errors: list[str] = field(default_factory=list)


class PublishTargetError(Exception):
    """Raised by target modules for actionable errors (name file + line + fix)."""
    def __init__(self, message: str, file_path: str | None = None, line: int | None = None):
        self.file_path = file_path
        self.line = line
        location = ''
        if file_path:
            location = f' [{file_path}' + (f':{line}' if line else '') + ']'
        super().__init__(f'{message}{location}')
