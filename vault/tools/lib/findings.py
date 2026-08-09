"""Typed validation findings and tally-by-construction primitives.

New or migrated check families must emit :class:`Finding` objects.  Rendering
the familiar ``[ERROR]``/``[WARN]`` text is an output concern; enforcement
reads ``Finding.severity`` directly and therefore cannot be defeated by a
missing or misleading message prefix.

Legacy string findings remain adaptable during the incremental migration of
the validator corpus.  The adapter is deliberately isolated here so no new
check needs to parse its own prose back into control flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable


class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    check_id: str
    subject: str
    message: str

    def render(self) -> str:
        subject = f"{self.subject} — " if self.subject else ""
        return f"  [{self.severity.value}] {subject}{self.message}"

    def __str__(self) -> str:
        return self.render()


_LEGACY_PREFIX = re.compile(r"^\s*\[(FAIL|ERROR|WARN|INFO)\]\s*", re.IGNORECASE)


def coerce_finding(
    value: Finding | str,
    *,
    default_severity: Severity = Severity.WARN,
    check_id: str = "legacy",
) -> Finding:
    """Convert a legacy string once at the migration boundary.

    New checks should construct ``Finding`` directly.  This compatibility
    path exists only so the 12K-line legacy corpus can migrate family by
    family without a flag day.
    """
    if isinstance(value, Finding):
        return value

    text = str(value).strip()
    match = _LEGACY_PREFIX.match(text)
    severity = default_severity
    if match:
        token = match.group(1).upper()
        severity = Severity.ERROR if token in {"FAIL", "ERROR"} else Severity(token)
        text = text[match.end():]
    return Finding(severity=severity, check_id=check_id, subject="", message=text)


@dataclass
class FindingTally:
    errors: int = 0
    warnings: int = 0
    infos: int = 0

    def add(self, value: Finding | str, *, check_id: str = "legacy") -> Finding:
        finding = coerce_finding(value, check_id=check_id)
        severity = finding.severity
        if severity == Severity.ERROR:
            self.errors += 1
        elif severity == Severity.WARN:
            self.warnings += 1
        else:
            self.infos += 1
        return finding

    def extend(
        self, values: Iterable[Finding | str], *, check_id: str = "legacy"
    ) -> list[Finding]:
        return [self.add(value, check_id=check_id) for value in values]


def tally_findings(
    values: Iterable[Finding | str], *, check_id: str = "legacy"
) -> tuple[list[Finding], FindingTally]:
    tally = FindingTally()
    typed = tally.extend(values, check_id=check_id)
    return typed, tally


def run_check_family(
    check_id: str,
    check: Callable,
    *args,
    **kwargs,
) -> tuple[list[Finding | str], int, int]:
    """Execute one standard ``(findings, checked, defects)`` family safely.

    A crashed check is itself an ERROR finding.  It cannot disappear through
    a broad exception handler or terminate before the summary tally observes
    it (Engine Law 12).
    """
    try:
        return check(*args, **kwargs)
    except Exception as exc:
        return (
            [
                Finding(
                    Severity.ERROR,
                    check_id,
                    getattr(check, "__name__", "check-family"),
                    f"check CRASHED: {exc.__class__.__name__}: {exc}",
                )
            ],
            0,
            1,
        )
