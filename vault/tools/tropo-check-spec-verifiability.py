#!/usr/bin/env python3
"""Can a locked spec's acceptance criteria actually be verified — at its own layer?

Built 2026-08-25 by argus-a157, on Mike's standing direction that every stoppage
must leave the machinery stronger rather than merely unblocked. It exists
because two stoppages in one day were both invisible until someone tripped over
them at the worst moment, and both were mechanically detectable the whole time.

STOPPAGE 1 — THE PHANTOM TARGET. Dev-spec 5b608d28's AC4 committed the test
`test_completion_reads_producers_v192.py`. The file had never existed, at any
commit, on any branch. It went unnoticed because the acceptance command is
`python3 -m pytest -q <file>`, and pytest on a missing path prints "no tests ran
in 0.00s" and EXITS 0. Inside a batch of six acceptance runs it reads as benign.
A criterion had been reported built with nothing behind it.

STOPPAGE 2 — THE LAYER CYCLE. Dev-spec 1a478c48's AC5 required a First-Use Walk
in "a customer-shaped studio built from the v1.92 candidate box". That made the
spec undeliverable in principle: the release-plan lock refuses any member that
is not `done`; the spec was a member; and the candidate box cannot be built
until the plan is locked. Lock needs done needs walk needs box needs lock. The
same spec's AC6 states the very principle AC5 broke — a dev cycle's verdict must
not depend on release machinery.

WHAT THIS CHECKS, THEREFORE, IS TWO THINGS:

    TARGETS EXIST     every path a verify command names is really there, and a
                      command that would pass vacuously is refused.
    LAYER IS HONEST   no dev-spec criterion is verified by an artifact that only
                      exists after the release containing that spec.

WHY IT IS A SEPARATE TOOL RATHER THAN A VALIDATOR CHECK. The validator is the
enforcement surface everyone runs and a large shared file; this wants its own
fixtures and its own both-directions proof first. Wiring it into the default
validator pass is the obvious next step and is deliberately not done in the same
gesture that introduces it.

    python3 vault/tools/tropo-check-spec-verifiability.py
    python3 vault/tools/tropo-check-spec-verifiability.py --uid 1a478c48
    python3 vault/tools/tropo-check-spec-verifiability.py --json

EXIT CODES, matching the preflight's contract deliberately (a crash is not a
verdict): 0 clean · 2 at least one finding · 3 could not reach an answer ·
4 misuse.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TOOLS = Path(__file__).resolve().parent
STUDIO_ROOT = TOOLS.parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib import fast_yaml  # noqa: E402

#: WHEN each check is meaningful. A locked spec legitimately names targets that
#: do not exist yet — that is what building is, and 10 of 5b608d28's 18
#: committed-substrate entries were change_class NEW at lock time. Running the
#: existence check at lock would therefore flag every freshly-locked spec, which
#: is the false-finding generator this file's own comments warn against.
#:
#: So the two checks answer different questions at different moments:
#:   AT LOCK   is any criterion unsatisfiable IN PRINCIPLE? Release-coupling is
#:             knowable the moment the criterion is written; no build changes it.
#:   AT CLOSE  does every named target actually exist? This is the question that
#:             matters when a spec claims done, and the one that would have
#:             caught 5b608d28 AC4's phantom target.
#: Found by argus-a157 an hour after building the tool, by asking what it would
#: have said about a spec on the day it was locked rather than today.
AT_LOCK = "lock"
AT_CLOSE = "close"
PHASES = (AT_LOCK, AT_CLOSE)

EXIT_OK = 0
EXIT_FINDINGS = 2
EXIT_OPERATIONAL = 3
EXIT_MISUSE = 4

#: Commands that report success when handed a path that does not exist. This is
#: the whole mechanism behind stoppage 1, so it is named rather than described.
VACUOUS_ON_MISSING = ("pytest",)

#: What a file reference looks like: a path ending in a short extension. Prose
#: containing a slash is not a path, and treating it as one produced seven false
#: PHANTOM-TARGETs on real specs.
_FILE_TOKEN_RE = re.compile(r"^[\w.\-/]+\.[A-Za-z0-9]{1,5}$")

#: A dev-spec criterion naming any of these is describing a release artifact —
#: something that exists only after the release which contains the spec. Kept
#: small and literal on purpose: a clever matcher here would produce false
#: findings on prose, and a false finding in a governance check is worse than a
#: missed one because it trains people to skip the check.
RELEASE_ARTIFACT_PHRASES = (
    "candidate box",
    "candidate sha",
    "the release candidate",
    "released box",
    "shipped box",
)


@dataclass
class Finding:
    uid: str
    criterion: str
    kind: str
    detail: str

    def render(self) -> str:
        return f"[{self.kind}] {self.uid} {self.criterion} — {self.detail}"


@dataclass
class SpecReport:
    uid: str
    title: str
    criteria: int = 0
    #: Criteria this tool COULD NOT inspect, because they are authored in the
    #: older prose shape — a bare list of strings with no verify block. Counted
    #: and reported, never silently skipped.
    #:
    #: This field exists because the first version DID silently skip them. Nine
    #: locked specs holding 32 criteria between them read as "0 criteria, 0
    #: findings" and the tool printed "clean". A reader written against one
    #: shape, quietly passing over another, green the whole time — the exact
    #: defect this instrument was built to catch, built into the instrument.
    #: Found by checking that the totals were plausible rather than trusting
    #: the word "clean".
    unreadable_shape: int = 0
    findings: List[Finding] = field(default_factory=list)


def _frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    text = path.read_text(errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        parsed = fast_yaml.safe_load(text[3:end])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _command_targets(command: str) -> List[str]:
    """Every file a verify command names, in either shape it is written in.

    TWO SHAPES, AND THE FIRST VERSION KNEW ONLY ONE. A path-shaped token
    (`vault/tools/tests/x.py`) and a DOTTED MODULE SELECTOR
    (`python3 -m unittest vault.tools.tests.x`) both name a file; only the
    first contains a separator. Recognising just the first produced 134
    NO-TARGET findings the moment this check was widened to closed specs —
    every one of them false, and every one on a command that runs perfectly.

    That is the third false-finding generator this file has produced in a day,
    and the same lesson each time: a governance check that cries wolf teaches
    people to skip it, so a rule that cannot distinguish "names nothing" from
    "names it in a shape I do not parse" is not ready to be enforced.

    Deliberately not a shell parser: this must not need to be correct about
    quoting to be useful about existence.
    """
    out = []
    tokens = [tk.strip("'\"`") for tk in str(command or "").split()]
    for i, token in enumerate(tokens):
        if token.startswith("-"):
            continue
        # A slash alone does not make a path. Prose in an evidence line —
        # "origin/main)", "status/state", "archived_at/archived_by;",
        # "boards/metis/;" — all contain one, and all were reported as missing
        # files. A file reference in a command looks like a file: it ends in an
        # extension.
        if "/" in token and _FILE_TOKEN_RE.match(token):
            out.append(token)
            continue
        # A dotted token is a target ONLY if it actually resolves to a module
        # file. Flagging one that does not is how "1.91.0" — a version string —
        # became a PHANTOM-TARGET, and how `npm run test:qa` became a missing
        # file. This check earns the right to speak about path-shaped targets,
        # where it cannot be wrong about what the token meant; everything else
        # is left alone rather than guessed at.
        if "." in token and not token.endswith(".py"):
            prior = tokens[i - 1] if i else ""
            if prior in ("unittest", "pytest"):
                out.append(token)
    return out


def _cd_roots(command: str) -> List[str]:
    """Directories a command changes into before running.

    `python3 a.py && cd tropo-app && npx tsx tests/x.ts` names a real file that
    resolves under tropo-app/, not under the studio root. Ignoring the `cd`
    reported it missing — the file is right there.
    """
    tokens = str(command or "").split()
    return [tokens[i + 1] for i, tk in enumerate(tokens)
            if tk == "cd" and i + 1 < len(tokens)]


def _resolves(studio_root: Path, target: str, command: str = "") -> bool:
    """Does this target name a file that exists, in either shape?

    A path token resolves directly. A dotted selector resolves by its longest
    MODULE PREFIX: `vault.tools.tests.test_x.SomeClass.test_method` names a
    file only as far as `test_x`, and converting every dot to a slash yields a
    path nothing could ever have. The first fix here did exactly that and
    turned 134 false NO-TARGETs into 132 false PHANTOM-TARGETs — a different
    wrong answer, not a right one.
    """
    if "/" in target:
        if (studio_root / target).exists():
            return True
        return any((studio_root / d / target).exists()
                   for d in _cd_roots(command))
    parts = target.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = studio_root / (Path(*parts[:cut]).as_posix() + ".py")
        if candidate.exists():
            return True
    return False

def _release_coupling(
    criterion: Dict[str, Any], studio_root: Path
) -> Optional[str]:
    """Is this criterion IMPOSSIBLE to verify at dev scope?

    THE SIGNAL IS THE VERIFY SIDE, NOT THE PROSE. The first version of this
    function matched release-artifact phrases anywhere in the criterion,
    including `behavior`, and its first run on real substrate produced a FALSE
    FINDING: 1a478c48 AC4 says "copy-pasteable in a bare shipped box", which is
    prose describing intent, while its verification is an automated dev-scope
    command that runs and passes today. A false finding in a governance check is
    worse than a missed one — it teaches people to skip the check — so the rule
    is now the narrow one that actually distinguishes the two cases.

    A criterion is release-coupled when BOTH hold:

      * it cannot be run at dev scope — the method is not automated, or the
        command names no target that resolves in this checkout; AND
      * its verification text names a release artifact.

    The retired 1a478c48 AC5 satisfied both (method: manual; "customer-shaped
    studio extracted from the v1.92 candidate"). AC4 satisfies neither, because
    it is automated and its target resolves. Prose alone never trips this.
    """
    verify = criterion.get("verify")
    if not isinstance(verify, dict):
        return None

    method = str(verify.get("method") or "").strip()
    command = str(verify.get("command") or "").strip()
    # Uses the same resolver as the existence check. It did not, and that
    # inconsistency alone produced a false RELEASE-COUPLED on cb194126: its
    # command is a dotted unittest selector, which resolves fine through
    # _resolves and not at all through a bare path join. Two functions in one
    # file disagreeing about whether a target resolves is this stream's own
    # defect, committed inside the tool built to catch it.
    runnable_here = method == "automated" and any(
        _resolves(studio_root, t, command) for t in _command_targets(command)
    )
    if runnable_here:
        return None

    lowered = " ".join(
        str(verify.get(k) or "") for k in ("command", "evidence")
    ).lower()
    for phrase in RELEASE_ARTIFACT_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def check_spec(path: Path, studio_root: Path,
               at: str = AT_CLOSE) -> Optional[SpecReport]:
    fm = _frontmatter(path)
    if fm is None or fm.get("type") != "dev-spec":
        return None
    # LOCKED **AND** DONE. Scoping to locked alone meant a spec dropped out of
    # this check the moment it closed — so the phantom-target class, which is
    # precisely a CLOSE-time question, could never be observed on a closed
    # spec. A `done` spec whose acceptance command names a deleted file is a
    # permanent false claim: the criterion reads as verified forever and the
    # command that would prove it cannot run.
    #
    # Found by watching the inspected count drop from 13 specs to 11 after
    # three closed, and asking where the other two went rather than reading the
    # smaller number as progress.
    if str(fm.get("status") or "") not in ("locked", "done"):
        return None

    report = SpecReport(uid=str(fm.get("uid") or path.stem),
                        title=str(fm.get("title") or "")[:70])
    criteria = fm.get("acceptance_criteria")
    if isinstance(criteria, str):
        # The oldest shape: the whole criteria set as one prose block. Not a
        # missing list — an unreadable one. Reporting it as "declares no
        # acceptance_criteria" was false on five real specs.
        report.unreadable_shape += 1
        return report
    if not isinstance(criteria, list):
        report.findings.append(
            Finding(report.uid, "-", "NO-CRITERIA",
                    "a locked dev-spec declares no acceptance_criteria list")
        )
        return report

    for criterion in criteria:
        if not isinstance(criterion, dict):
            # Older prose shape: a bare string, no verify block. Cannot be
            # inspected; counted so the report never overstates coverage.
            report.unreadable_shape += 1
            continue
        cid = str(criterion.get("id") or "?")
        report.criteria += 1
        verify = criterion.get("verify")
        if not isinstance(verify, dict):
            report.findings.append(
                Finding(report.uid, cid, "NO-VERIFY",
                        "criterion declares no verify block")
            )
            continue

        method = str(verify.get("method") or "").strip()
        command = str(verify.get("command") or "").strip()

        if method == "automated":
            if not command and at == AT_CLOSE:
                report.findings.append(
                    Finding(report.uid, cid, "NO-COMMAND",
                            "automated criterion names no command")
                )
            targets = _command_targets(command)
            # NO IMPLICIT "no target" FINDING. A command with no path token is
            # not evidence of anything: `npm test`, `cd app && npm run test:qa`
            # and a dotted selector are all runnable and all path-free. The
            # first version emitted a finding for each, 134 of them, every one
            # false. What this check can be RIGHT about is a path-shaped target
            # that does not exist — so that is all it claims.
            for target in targets:
                if at != AT_CLOSE:
                    continue  # a locked spec may name what is not built yet
                if _resolves(studio_root, target, command):
                    continue
                vacuous = any(v in command for v in VACUOUS_ON_MISSING)
                report.findings.append(
                    Finding(
                        report.uid, cid,
                        "PHANTOM-TARGET-SILENT" if vacuous else "PHANTOM-TARGET",
                        f"names {target}, which does not exist"
                        + (
                            " — and the runner reports success on a missing "
                            "path, so this criterion passes vacuously"
                            if vacuous else ""
                        ),
                    )
                )

        phrase = _release_coupling(criterion, studio_root)
        if phrase:
            report.findings.append(
                Finding(
                    report.uid, cid, "RELEASE-COUPLED",
                    f"is verified against {phrase!r} — an artifact that exists "
                    f"only after the release containing this spec. A dev-spec "
                    f"criterion must be verifiable at dev scope; re-home it as "
                    f"a ship criterion of the release plan",
                )
            )

    return report


def run(studio_root: Path, only_uid: Optional[str] = None,
        at: str = AT_CLOSE) -> List[SpecReport]:
    files = studio_root / "vault" / "files"
    if not files.is_dir():
        raise FileNotFoundError(f"no vault/files under {studio_root}")
    reports = []
    paths = (
        [files / f"{only_uid}.md"] if only_uid else sorted(files.glob("*.md"))
    )
    for path in paths:
        if not path.is_file():
            continue
        report = check_spec(path, studio_root, at)
        if report is not None:
            reports.append(report)
    return reports


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--studio-root", default=str(STUDIO_ROOT))
    parser.add_argument("--uid", help="check one spec by uid")
    parser.add_argument("--at", choices=list(PHASES), default=AT_CLOSE,
                        help="lock: structural checks only (a locked spec may name "
                             "targets not yet built). close: everything, including "
                             "that every named target exists.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.studio_root).resolve()
    try:
        reports = run(root, args.uid, args.at)
    except FileNotFoundError as exc:
        print(f"[MISUSE] {exc}", file=sys.stderr)
        return EXIT_MISUSE
    except Exception as exc:  # noqa: BLE001 — could not reach an answer
        print(f"[OPERATIONAL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    findings = [f for r in reports for f in r.findings]

    if args.json:
        print(json.dumps({
            "specs_checked": len(reports),
            "criteria_checked": sum(r.criteria for r in reports),
            "findings": [
                {"uid": f.uid, "criterion": f.criterion, "kind": f.kind,
                 "detail": f.detail}
                for f in findings
            ],
        }, indent=2))
        return EXIT_FINDINGS if findings else EXIT_OK

    unreadable = sum(r.unreadable_shape for r in reports)
    print(f"--- locked dev-spec verifiability: {len(reports)} spec(s), "
          f"{sum(r.criteria for r in reports)} criteria inspected ---")
    if unreadable:
        # Never print "clean" over criteria this tool cannot read. Coverage it
        # does not have is the one thing a governance check must not imply.
        blind = [r for r in reports if r.unreadable_shape]
        print(f"[NOT INSPECTED] {unreadable} criteria across {len(blind)} spec(s) "
              f"are authored in the older prose shape (a bare list of strings, "
              f"no verify block) and cannot be checked: "
              + ", ".join(f"{r.uid}({r.unreadable_shape})" for r in blind))
    if not findings:
        print("clean over what was inspected — every criterion inspected names a "
              "target that exists, and none is verified by an artifact of its "
              "own release")
        return EXIT_OK
    for finding in findings:
        print(finding.render())
    print(f"\n{len(findings)} finding(s)")
    return EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
