#!/usr/bin/env python3
"""---
uid: 1e4cf4e2
name: release-validation-gate
type: tool
status: active
owner: argus
domain: "Capture and compare full release-validator evidence inside one activation's governed run folder."
spawnable_by:
  - all-executives
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-release-validation-gate.py"
script_path: vault/tools/tropo-release-validation-gate.py
input:
  type: object
  required:
    - mode
    - activation_uid
  properties:
    mode:
      type: string
      enum: [capture, compare]
    activation_uid:
      type: string
      pattern: "^[0-9a-f]{8}$"
output:
  type: object
  required: [verdict, run_uid]
  properties:
    verdict:
      type: string
      enum: [pass, fail, refused, operational-error]
    run_uid:
      type: string
writes_scope:
  - vault/pipeline-runs/*/release-validation-*
audit_required: true
governance_category: lifecycle
version: 1.0.0
created: 2026-08-14
created_by: argus-a148
modified: 2026-08-14
modified_by: argus-a148
governed_by: d5e1b4a3
member_of:
  - 952f3aa3
schema_version: 2
extraction_scope: ship
capsule_version: '1.3'
title: "release-validation-gate — Baseline and compare the full release validator"
trigger_description: "Capture or compare activation-bound full-validator release evidence without making known Studio debt an absolute gate."
---

# release-validation-gate

## Intent

The source Studio has known validator debt, so an absolute ``exit == 0`` gate
would refuse every release without distinguishing old debt from a regression.
This tool records the full release-mode result at release fan-in, then refuses
the final release state only when it introduces a new failure/error. It is not
a general validator wrapper and must not be used without a release activation.

## Invocation Protocol

Capture at release Assemble fan-in:

    python3 vault/tools/tropo-release-validation-gate.py capture \
        --activation-uid <uid>

Compare at final release Verify:

    python3 vault/tools/tropo-release-validation-gate.py compare \
        --activation-uid <uid>

## Input / Output

Input is one explicit release activation UID plus the ``capture`` or ``compare``
mode. Output is an exit-code verdict and run-folder evidence: complete logs,
structured baseline JSON, and structured comparison JSON.

## Governance

The activation, pipeline run, reverse binding, and Studio-relative run folder
must all resolve and agree. Writes use fixed filenames only inside that governed
run folder. The baseline is never rebased; a valid existing baseline is reused.

## Verification

Capture succeeds only after the fixed AC5 unittest passes and the full validator
completes with exit 0 or 1 plus its terminal Summary. Compare passes only when
section counts and exact ANSI-stripped finding signatures introduce no debt.

## Failure Modes

Missing/mismatched bindings and missing baseline evidence refuse. Validator
timeout, launch failure, exit outside 0/1, or missing terminal Summary is an
operational error. New sections, increased counts, and new exact findings fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PIPELINE_UID = "634913c2"
UID_RE = re.compile(r"^[0-9a-f]{8}$")
ANSI_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
)
SECTION_RE = re.compile(r"^\s*---\s+(.+?)\s+---\s*$")
SEVERITY_RE = re.compile(r"^\s*\[(FAIL|ERROR)\]\s*(.*)$")
SUMMARY_RE = re.compile(
    r"^Summary:\s*(\d+)\s+passed,\s*(\d+)\s+failed,\s*"
    r"(\d+)\s+warnings,\s*(\d+)\s+normalizable\s*$"
)

AC5_COMMAND = (
    "python3",
    "-m",
    "unittest",
    "vault.tools.tests.test_two_pipeline_split_0a0a6777."
    "RemainingAcceptanceCriteria.test_ac05_fan_in_row_and_reservation_gate",
)
VALIDATOR_COMMAND = (
    "python3",
    "vault/tools/tropo-validate.py",
    "--release",
)

AC5_LOG = "release-validation-ac5.log"
BASELINE_LOG = "release-validation-baseline.log"
BASELINE_REPORT = "release-validation-baseline.json"
CURRENT_LOG = "release-validation-current.log"
COMPARISON_REPORT = "release-validation-comparison.json"

SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_OPERATIONAL_ERROR = 2

_COUNT_NOUNS = (
    r"defects?|violations?|failures?|errors?|findings?|leaks?|collisions?|"
    r"regressions?|occurrences?|references?|drift(?:\s+findings?)?"
)
_AGGREGATE_COUNT_RE = re.compile(
    rf"\b(\d+)\s+(?:[A-Za-z0-9_.:/<>-]+\s+){{0,6}}(?:{_COUNT_NOUNS})\b",
    re.IGNORECASE,
)
_AGGREGATE_STATE_RE = re.compile(
    r"(?:^|;)\s*(\d+)\s+(?:have|has|missing|broken|stale|"
    r"non-resolving|invisible|cannot)\b",
    re.IGNORECASE,
)
_AGGREGATE_HAS_RE = re.compile(
    rf"\b(?:has|have|contains|found|reported|produced)\s+(\d+)\s+"
    rf"(?:[A-Za-z0-9_.:/<>-]+\s+){{0,6}}(?:{_COUNT_NOUNS})\b",
    re.IGNORECASE,
)
_IDENTITY_RE = re.compile(
    r"(?:^|\s)(?:\.{0,2}/|[A-Za-z0-9_.-]+/)\S+|"
    r"\b[0-9a-f]{8}\b"
)


class GateRefusal(RuntimeError):
    """The requested activation cannot safely satisfy this release gate."""


class OperationalError(RuntimeError):
    """A command or audit surface did not complete reliably."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateRefusal(f"cannot read governed entry {path}: {exc}") from exc
    if not text.startswith("---\n"):
        raise GateRefusal(f"{path} has no governed frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise GateRefusal(f"{path} has unterminated frontmatter")
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise GateRefusal(f"{path} frontmatter does not parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise GateRefusal(f"{path} frontmatter is not a mapping")
    return parsed


def resolve_release_run(activation_uid: str, studio_root: Path = ROOT) -> dict:
    """Resolve activation -> run -> run_folder and require every link to agree."""
    root = Path(studio_root).resolve()
    activation_uid = str(activation_uid or "").strip()
    if not UID_RE.fullmatch(activation_uid):
        raise GateRefusal(
            f"{activation_uid!r} is not an 8-character lowercase hex activation UID"
        )

    files = root / "vault" / "files"
    activation_path = files / f"{activation_uid}.md"
    if not activation_path.is_file():
        raise GateRefusal(
            f"activation {activation_uid} does not resolve at {activation_path}"
        )
    activation = _frontmatter(activation_path)
    if str(activation.get("uid") or "") != activation_uid:
        raise GateRefusal(
            f"activation file {activation_path} declares UID "
            f"{activation.get('uid')!r}, not {activation_uid}"
        )
    if str(activation.get("type") or "") != "activation":
        raise GateRefusal(
            f"{activation_uid} is type {activation.get('type')!r}, not activation"
        )
    activation_pipeline = str(
        activation.get("pipeline")
        or activation.get("pipeline_uid")
        or activation.get("agent_root")
        or ""
    )
    if activation_pipeline != RELEASE_PIPELINE_UID:
        raise GateRefusal(
            f"activation {activation_uid} belongs to pipeline "
            f"{activation_pipeline or '(unset)'}, not release pipeline "
            f"{RELEASE_PIPELINE_UID}"
        )

    run_uid = str(activation.get("pipeline_run_uid") or "").strip()
    if not UID_RE.fullmatch(run_uid):
        raise GateRefusal(
            f"activation {activation_uid} names invalid pipeline_run_uid {run_uid!r}"
        )
    run_path = files / f"{run_uid}.md"
    if not run_path.is_file():
        raise GateRefusal(
            f"activation {activation_uid} names run {run_uid}, which does not "
            f"resolve at {run_path}"
        )
    run = _frontmatter(run_path)
    if str(run.get("uid") or "") != run_uid:
        raise GateRefusal(
            f"run file {run_path} declares UID {run.get('uid')!r}, not {run_uid}"
        )
    if str(run.get("type") or "") != "pipeline-run":
        raise GateRefusal(f"{run_uid} is type {run.get('type')!r}, not pipeline-run")
    run_pipeline = str(run.get("pipeline") or run.get("pipeline_uid") or "")
    if run_pipeline != RELEASE_PIPELINE_UID:
        raise GateRefusal(
            f"run {run_uid} belongs to pipeline {run_pipeline or '(unset)'}, "
            f"not release pipeline {RELEASE_PIPELINE_UID}"
        )

    backrefs = {
        field: str(run.get(field) or "").strip()
        for field in ("activation", "activation_uid", "substrate_authored_by")
        if str(run.get(field) or "").strip()
    }
    if not backrefs:
        raise GateRefusal(
            f"run {run_uid} carries no activation back-reference; refusing an "
            "unbound run folder"
        )
    disagreements = {
        field: value for field, value in backrefs.items() if value != activation_uid
    }
    if disagreements:
        detail = ", ".join(f"{field}={value}" for field, value in disagreements.items())
        raise GateRefusal(
            f"activation/run binding disagreement: {activation_uid} names "
            f"{run_uid}, but the run declares {detail}"
        )

    declared_folder = str(run.get("run_folder") or "").strip()
    relative = Path(declared_folder)
    if (
        not declared_folder
        or relative.is_absolute()
        or len(relative.parts) < 3
        or tuple(relative.parts[:2]) != ("vault", "pipeline-runs")
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise GateRefusal(
            f"run {run_uid} declares unsafe run_folder {declared_folder!r}; "
            "release evidence may be written only under vault/pipeline-runs/"
        )
    runs_root = (root / "vault" / "pipeline-runs").resolve()
    run_folder = (root / relative).resolve()
    try:
        run_folder.relative_to(runs_root)
    except ValueError as exc:
        raise GateRefusal(
            f"run {run_uid} declares run_folder outside {runs_root}: {declared_folder}"
        ) from exc
    if not run_folder.is_dir():
        raise GateRefusal(
            f"run {run_uid} declares missing run_folder {declared_folder}"
        )

    return {
        "activation_uid": activation_uid,
        "run_uid": run_uid,
        "run_folder": run_folder,
        "run_folder_relative": relative.as_posix(),
    }


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
) -> dict:
    command = tuple(str(part) for part in command)
    started_at = _utc_now()
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OperationalError(
            f"command timed out after {timeout}s: {shlex.join(command)}"
        ) from exc
    except OSError as exc:
        raise OperationalError(
            f"could not execute {shlex.join(command)}: {exc}"
        ) from exc

    stdout = result.stdout or b""
    stderr = result.stderr or b""
    combined = stdout + b"\n--- STDERR ---\n" + stderr
    return {
        "command": shlex.join(command),
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "output_sha256": _sha256(combined),
        "started_at": started_at,
        "finished_at": _utc_now(),
    }


def _render_process_log(process: dict) -> bytes:
    header = (
        f"$ {process['command']}\n"
        f"exit_code: {process['exit_code']}\n"
        f"output_sha256: {process['output_sha256']}\n"
        f"started_at: {process['started_at']}\n"
        f"finished_at: {process['finished_at']}\n"
        "--- STDOUT ---\n"
    ).encode("utf-8")
    return (
        header
        + process["stdout"]
        + b"\n--- STDERR ---\n"
        + process["stderr"]
        + b"\n"
    )


def _process_record(process: dict, log_name: str, log_bytes: bytes) -> dict:
    return {
        "command": process["command"],
        "exit_code": process["exit_code"],
        "output_sha256": process["output_sha256"],
        "started_at": process["started_at"],
        "finished_at": process["finished_at"],
        "log": log_name,
        "log_sha256": _sha256(log_bytes),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_json(path: Path, payload: dict) -> None:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    _atomic_write(path, encoded)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateRefusal(f"cannot read release-gate report {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateRefusal(f"release-gate report {path} is not a JSON object")
    return value


def _is_aggregate_finding(payload: str) -> bool:
    """Separate tally prose from exact finding identities.

    Aggregate lines change text when a section improves (for example,
    ``[FAIL] 20 checked; 3 defects`` -> ``2 defects``). They contribute their
    numeric tally but are not signatures. All non-aggregate lines remain exact
    after ANSI removal; UIDs, paths, and other identity-bearing text are never
    generalized away.
    """
    if not re.search(r"\d", payload):
        return False
    if not re.match(r"^\d+\b", payload) and _IDENTITY_RE.search(payload):
        return False
    if re.match(r"^\d+\b", payload) and re.search(
        rf"\b(?:{_COUNT_NOUNS}|unresolved|missing|broken|stale|"
        r"non-resolving|invisible|cannot|have\s+NO)\b",
        payload,
        re.IGNORECASE,
    ):
        return True
    return bool(
        _AGGREGATE_COUNT_RE.search(payload)
        or _AGGREGATE_STATE_RE.search(payload)
        or _AGGREGATE_HAS_RE.search(payload)
    )


def _aggregate_failure_count(payload: str) -> int:
    candidates: list[int] = []
    candidates.extend(int(value) for value in _AGGREGATE_COUNT_RE.findall(payload))
    candidates.extend(int(value) for value in _AGGREGATE_STATE_RE.findall(payload))
    candidates.extend(int(value) for value in _AGGREGATE_HAS_RE.findall(payload))
    if candidates:
        return max(candidates)
    leading = re.match(r"^(\d+)\b", payload)
    return int(leading.group(1)) if leading else 0


def parse_validator_output(output: str) -> dict:
    """Return section-local failure evidence, normalizing ANSI and nothing else."""
    clean = ANSI_RE.sub("", output)
    sections: dict[str, dict] = {}
    current_section = "(validator preamble)"
    sections[current_section] = _empty_section()
    summary = None

    for line in clean.splitlines():
        heading = SECTION_RE.match(line)
        if heading:
            current_section = heading.group(1)
            sections.setdefault(current_section, _empty_section())
            continue
        summary_match = SUMMARY_RE.match(line)
        if summary_match:
            summary = {
                "passed": int(summary_match.group(1)),
                "failed": int(summary_match.group(2)),
                "warnings": int(summary_match.group(3)),
                "normalizable": int(summary_match.group(4)),
            }
            continue
        severity_match = SEVERITY_RE.match(line)
        if not severity_match:
            continue
        severity, payload = severity_match.groups()
        section = sections[current_section]
        count_key = "failure_line_count" if severity == "FAIL" else "error_line_count"
        reported_key = (
            "reported_failure_count" if severity == "FAIL"
            else "reported_error_count"
        )
        section[count_key] += 1
        if _is_aggregate_finding(payload):
            section["aggregate_lines"].append(line)
            section[reported_key] += _aggregate_failure_count(payload)
        else:
            section["specific_findings"].append(line)

    if summary is None:
        raise OperationalError(
            "validator exited without its terminal Summary line; execution did "
            "not complete as a validator result"
        )
    return {"summary": summary, "sections": sections}


def _empty_section() -> dict:
    return {
        "failure_line_count": 0,
        "error_line_count": 0,
        "reported_failure_count": 0,
        "reported_error_count": 0,
        "specific_findings": [],
        "aggregate_lines": [],
    }


def _completed_validator(process: dict) -> dict:
    if process["exit_code"] not in (0, 1):
        raise OperationalError(
            f"validator exited {process['exit_code']}; only 0 (clean) or 1 "
            "(completed with findings) is a validator result"
        )
    parsed = parse_validator_output(
        process["stdout"].decode("utf-8", errors="replace")
    )
    has_failures = parsed["summary"]["failed"] > 0
    if (process["exit_code"] == 1) != has_failures:
        raise OperationalError(
            "validator exit code and terminal failed count disagree"
        )
    return parsed


def _git_commit(studio_root: Path) -> str:
    try:
        result = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=str(studio_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OperationalError(f"cannot capture validator git commit: {exc}") from exc
    commit = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise OperationalError(
            f"cannot capture validator git commit: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return commit


def _validate_log(run_folder: Path, record: dict, expected_name: str) -> None:
    if record.get("log") != expected_name:
        raise GateRefusal(
            f"baseline names log {record.get('log')!r}; expected {expected_name}"
        )
    path = run_folder / expected_name
    if not path.is_file():
        raise GateRefusal(f"baseline evidence log is missing: {path}")
    actual = _sha256(path.read_bytes())
    if actual != record.get("log_sha256"):
        raise GateRefusal(
            f"baseline evidence log hash mismatch for {path}; refusing a "
            "baseline whose full output no longer matches its report"
        )


def _load_valid_baseline(
    binding: dict,
    *,
    validator_command: Sequence[str],
) -> dict:
    path = binding["run_folder"] / BASELINE_REPORT
    if not path.is_file():
        raise GateRefusal(
            f"run {binding['run_uid']} has no captured release-validator "
            f"baseline at {path}"
        )
    report = _read_json(path)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": "release-validation-baseline",
        "activation_uid": binding["activation_uid"],
        "run_uid": binding["run_uid"],
        "run_folder": binding["run_folder_relative"],
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise GateRefusal(
                f"baseline binding mismatch: {field} is "
                f"{report.get(field)!r}, expected {value!r}"
            )
    ac5 = report.get("ac5")
    validator = report.get("validator")
    if not isinstance(ac5, dict) or not isinstance(validator, dict):
        raise GateRefusal("baseline is missing structured AC5/validator evidence")
    if ac5.get("exit_code") != 0:
        raise GateRefusal("baseline records a non-passing AC5 verifier")
    if validator.get("exit_code") not in (0, 1):
        raise GateRefusal("baseline does not record a completed validator result")
    if validator.get("command") != shlex.join(tuple(validator_command)):
        raise GateRefusal(
            "baseline validator command differs from the production command; "
            "refusing to compare unlike instruments"
        )
    evidence = validator.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("sections"), dict):
        raise GateRefusal("baseline carries no structured section evidence")
    _validate_log(binding["run_folder"], ac5, AC5_LOG)
    _validate_log(binding["run_folder"], validator, BASELINE_LOG)
    return report


def capture_baseline(
    activation_uid: str,
    *,
    studio_root: Path = ROOT,
    ac5_command: Sequence[str] = AC5_COMMAND,
    validator_command: Sequence[str] = VALIDATOR_COMMAND,
    now: Callable[[], str] = _utc_now,
    commit: str | None = None,
) -> dict:
    """Run AC5 and create one immutable baseline for this release run."""
    root = Path(studio_root).resolve()
    binding = resolve_release_run(activation_uid, root)
    baseline_path = binding["run_folder"] / BASELINE_REPORT

    existing = None
    if baseline_path.is_file():
        existing = _load_valid_baseline(
            binding, validator_command=validator_command
        )

    ac5_process = _run_command(ac5_command, cwd=root, timeout=300)
    if ac5_process["exit_code"] != 0:
        ac5_log = _render_process_log(ac5_process)
        if existing is None:
            _atomic_write(binding["run_folder"] / AC5_LOG, ac5_log)
        raise GateRefusal(
            f"AC5 fan-in verifier failed with exit {ac5_process['exit_code']}; "
            "a release baseline cannot be captured before fan-in is valid"
        )
    if existing is not None:
        return existing

    ac5_log = _render_process_log(ac5_process)
    _atomic_write(binding["run_folder"] / AC5_LOG, ac5_log)

    validator_process = _run_command(validator_command, cwd=root, timeout=3600)
    validator_log = _render_process_log(validator_process)
    _atomic_write(binding["run_folder"] / BASELINE_LOG, validator_log)
    parsed = _completed_validator(validator_process)

    captured_commit = commit or _git_commit(root)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "release-validation-baseline",
        "activation_uid": binding["activation_uid"],
        "run_uid": binding["run_uid"],
        "run_folder": binding["run_folder_relative"],
        "captured_at": now(),
        "captured_commit": captured_commit,
        "ac5": _process_record(ac5_process, AC5_LOG, ac5_log),
        "validator": {
            **_process_record(
                validator_process, BASELINE_LOG, validator_log
            ),
            "evidence": parsed,
        },
    }
    _write_json(baseline_path, report)
    return report


def compare_evidence(baseline: dict, current: dict) -> list[dict]:
    """Return only regressions; lower counts and removed signatures are safe."""
    regressions: list[dict] = []
    baseline_summary = baseline.get("summary") or {}
    current_summary = current.get("summary") or {}
    if int(current_summary.get("failed", 0)) > int(
        baseline_summary.get("failed", 0)
    ):
        regressions.append(
            {
                "kind": "aggregate-failed-count-increased",
                "baseline": int(baseline_summary.get("failed", 0)),
                "current": int(current_summary.get("failed", 0)),
            }
        )

    baseline_sections = baseline.get("sections") or {}
    current_sections = current.get("sections") or {}
    for section_name in sorted(set(baseline_sections) | set(current_sections)):
        before = baseline_sections.get(section_name, _empty_section())
        after = current_sections.get(section_name, _empty_section())
        has_current_failure = (
            int(after.get("failure_line_count", 0))
            + int(after.get("error_line_count", 0))
        ) > 0
        if section_name not in baseline_sections and has_current_failure:
            regressions.append(
                {
                    "kind": "new-failing-section",
                    "section": section_name,
                }
            )

        for severity, line_key, reported_key in (
            ("FAIL", "failure_line_count", "reported_failure_count"),
            ("ERROR", "error_line_count", "reported_error_count"),
        ):
            before_lines = int(before.get(line_key, 0))
            after_lines = int(after.get(line_key, 0))
            if after_lines > before_lines:
                regressions.append(
                    {
                        "kind": "section-severity-line-count-increased",
                        "section": section_name,
                        "severity": severity,
                        "baseline": before_lines,
                        "current": after_lines,
                    }
                )
            before_reported = int(before.get(reported_key, 0))
            after_reported = int(after.get(reported_key, 0))
            if after_reported > before_reported:
                regressions.append(
                    {
                        "kind": "section-reported-count-increased",
                        "section": section_name,
                        "severity": severity,
                        "baseline": before_reported,
                        "current": after_reported,
                    }
                )

        before_findings = Counter(before.get("specific_findings") or [])
        after_findings = Counter(after.get("specific_findings") or [])
        for signature, count in sorted((after_findings - before_findings).items()):
            regressions.append(
                {
                    "kind": "new-specific-finding",
                    "section": section_name,
                    "signature": signature,
                    "count": count,
                }
            )
    return regressions


def compare_current(
    activation_uid: str,
    *,
    studio_root: Path = ROOT,
    validator_command: Sequence[str] = VALIDATOR_COMMAND,
    now: Callable[[], str] = _utc_now,
    commit: str | None = None,
) -> dict:
    """Run the final validator, preserve its output, and compare to fan-in."""
    root = Path(studio_root).resolve()
    binding = resolve_release_run(activation_uid, root)
    baseline = _load_valid_baseline(
        binding, validator_command=validator_command
    )

    current_process = _run_command(validator_command, cwd=root, timeout=3600)
    current_log = _render_process_log(current_process)
    _atomic_write(binding["run_folder"] / CURRENT_LOG, current_log)
    compared_at = now()
    compared_commit = commit or _git_commit(root)

    try:
        current_evidence = _completed_validator(current_process)
    except OperationalError as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": "release-validation-comparison",
            "activation_uid": binding["activation_uid"],
            "run_uid": binding["run_uid"],
            "run_folder": binding["run_folder_relative"],
            "compared_at": compared_at,
            "compared_commit": compared_commit,
            "baseline": {
                "captured_at": baseline["captured_at"],
                "captured_commit": baseline["captured_commit"],
                "output_sha256": baseline["validator"]["output_sha256"],
                "log": baseline["validator"]["log"],
            },
            "current": _process_record(
                current_process, CURRENT_LOG, current_log
            ),
            "regressions": [
                {"kind": "validator-operational-error", "detail": str(exc)}
            ],
            "verdict": "operational-error",
        }
        _write_json(binding["run_folder"] / COMPARISON_REPORT, report)
        return report

    baseline_evidence = baseline["validator"]["evidence"]
    regressions = compare_evidence(baseline_evidence, current_evidence)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "release-validation-comparison",
        "activation_uid": binding["activation_uid"],
        "run_uid": binding["run_uid"],
        "run_folder": binding["run_folder_relative"],
        "compared_at": compared_at,
        "compared_commit": compared_commit,
        "baseline": {
            "captured_at": baseline["captured_at"],
            "captured_commit": baseline["captured_commit"],
            "exit_code": baseline["validator"]["exit_code"],
            "output_sha256": baseline["validator"]["output_sha256"],
            "log": baseline["validator"]["log"],
            "summary": baseline_evidence["summary"],
        },
        "current": {
            **_process_record(current_process, CURRENT_LOG, current_log),
            "evidence": current_evidence,
        },
        "regressions": regressions,
        "verdict": "pass" if not regressions else "fail",
    }
    _write_json(binding["run_folder"] / COMPARISON_REPORT, report)
    return report


def _baseline_message(report: dict) -> str:
    summary = report["validator"]["evidence"]["summary"]
    return (
        "PASS: release validator baseline captured "
        f"(activation={report['activation_uid']}, run={report['run_uid']}, "
        f"validator_exit={report['validator']['exit_code']}, "
        f"failed={summary['failed']})"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "compare"):
        command = subparsers.add_parser(mode)
        command.add_argument("--activation-uid", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "capture":
            report = capture_baseline(args.activation_uid)
            print(_baseline_message(report))
            return EXIT_OK

        report = compare_current(args.activation_uid)
        if report["verdict"] == "pass":
            current = report["current"]["evidence"]["summary"]
            print(
                "PASS: no new release-validator failures/errors "
                f"(activation={report['activation_uid']}, "
                f"run={report['run_uid']}, failed={current['failed']})"
            )
            return EXIT_OK
        if report["verdict"] == "operational-error":
            print(
                f"ERROR: validator did not complete operationally; see "
                f"{report['run_folder']}/{COMPARISON_REPORT}",
                file=sys.stderr,
            )
            return EXIT_OPERATIONAL_ERROR
        print(
            f"REFUSED: {len(report['regressions'])} new release-validator "
            f"failure/error condition(s); see "
            f"{report['run_folder']}/{COMPARISON_REPORT}",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    except GateRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except OperationalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
