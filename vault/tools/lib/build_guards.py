"""The build's guards as pure checks — one definition, two readers.

v1.95 Spine B (f015997f8d8e, argus-a171 spike 2026-09-05). tropo-build-release.py
carried its guards as print-and-exit functions called in sequence, so the box
failed at the FIRST guard each attempt (v1.94: eight attempts) and the release
preflight — the registry built for exactly this in 2fae6312 — could not see
them. A guard registered as a Gate must run in the preflight's process, which
must not import a 4,500-line build tool to ask one question. So each guard's
decision lives here as a function returning the list of problems it found
(empty means pass), and both readers consume that:

  * tropo-build-release.py keeps its print-and-exit wrapper around the check
    until Step 11 runs the candidate phase through the registry;
  * tropo-release-preflight.py wraps the same check in a Gate verifier.

The refusal texts and the markers are defined ONCE, here. A guard that lists
its markers in the build tool and again in the preflight is the two-readers
defect this spine exists to remove.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

__all__ = [
    "MISSION_BRIEF_LEAK_MARKERS",
    "MISSION_BRIEF_SLOT_REL",
    "mission_brief_slot_problems",
]

#: The shipped boot slot that is BOTH a required read and a confidentiality
#: surface (task 2ffda37e defect #1): Argo's real crew brief once shipped
#: verbatim as every customer studio's own mission.
MISSION_BRIEF_SLOT_REL = os.path.join(".tropo-studio", "mission-brief.md")

#: Argo-internal markers that must never appear in the shipped slot. Drawn
#: from the leak's own content (2ffda37e defect #1 §Verification).
MISSION_BRIEF_LEAK_MARKERS = (
    "argo", "metis", "hollow economy", "agentic builders", "culture is the moat",
)

# Word-boundary matched, not substring: a bare `'argo' in body` also fires on
# "cargo", "embargo" and "Argonaut", which would fail a release build with a
# confidentiality message about a word the template is entitled to use.
_MISSION_BRIEF_LEAK_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in MISSION_BRIEF_LEAK_MARKERS) + r")\b",
    re.IGNORECASE,
)


def mission_brief_slot_problems(build_dir) -> List[str]:
    """Every reason the shipped mission-brief slot must not seal; [] is pass.

    absent  -> every customer agent hits a missing required read at Step 2.3
               (activation playbook 99341618) / Tier-2 read-at-every-boot;
    real prose -> whatever is in it becomes the mission every agent in that
               studio boots on. Only a `<FILL: …>` template satisfies both.
    """
    slot = Path(build_dir) / MISSION_BRIEF_SLOT_REL
    if not slot.is_file():
        return [
            "%s absent from the build — a Required:Yes boot read (99341618 Step 2.3 "
            "+ cf8c3be9 Tier 2); a box without it breaks first boot for every "
            "customer agent. Check Step 7.1 and that Step 7 did not clobber it."
            % MISSION_BRIEF_SLOT_REL
        ]
    body = slot.read_text(encoding="utf-8")
    problems: List[str] = []
    if "<FILL:" not in body:
        problems.append(
            "no <FILL: …> placeholders — the slot is not the generic template. "
            "Whatever is in it becomes the mission every agent in a customer "
            "studio boots on."
        )
    hits = sorted({m.group(0).lower() for m in _MISSION_BRIEF_LEAK_RE.finditer(body)})
    if hits:
        problems.append("Argo-internal marker(s) present: %s" % hits)
    return problems


# ── The box guards that were direct calls in tropo-build-release.py ──────────
# Each returns the list of problems it found; [] is pass. The build tool's
# print-and-exit wrappers and the preflight's Gate verifiers both read these.

SHIPPED_SURFACES = (
    "00-tropo-nav", "01-studio-inbox", "02-outbox", "03-design",
    "04-external-work", "99-recycle",
)


def shipped_surfaces_problems(build_dir) -> List[str]:
    """RT1/RT2 (argus-a118, v1.74; finding 1ee11d09): a release MUST carry its
    declared human-navigation + workspace surfaces. Both shipped silently
    missing in Mike's v1.74 release walk."""
    box = Path(build_dir)
    problems = [d for d in SHIPPED_SURFACES if not (box / d).is_dir()]
    nav = box / "00-tropo-nav"
    if nav.is_dir() and not any(nav.iterdir()):
        problems.append("00-tropo-nav (present but EMPTY — nav regen produced nothing)")
    return problems


def stale_system_dir_problems(build_dir) -> List[str]:
    """One Home retirement (ADR-045): ALL of system/ must be absent from the box
    and vault/updates/ must be present — the two moved together."""
    box = Path(build_dir)
    stale_dir = box / "system"
    updates_dir = box / "vault" / "updates"
    problems: List[str] = []
    if stale_dir.is_dir():
        contents = [str(p.relative_to(box)) for p in stale_dir.rglob("*") if p.is_file()]
        if contents:
            problems.append(
                "system/ shipped (%d file(s)) — dissolved by ADR-045 One Home "
                "(system/updates/ at Gate 2; system/vault-steward/ at v1.80 S3). "
                "Check c5f8a193 + e7c2a851 are source_mode:skip and a3d7b248 + "
                "b94e3d72 output_path is vault/tropo-vault-steward/. Sample: %s"
                % (len(contents), contents[:5])
            )
    if not updates_dir.is_dir() or not any(updates_dir.iterdir()):
        problems.append(
            "vault/updates/ missing or empty — the Gate-2 update apply state machine "
            "did not ship (see step_3e_copy_vault_updates)."
        )
    return problems


def studio_identity_problems(build_dir) -> List[str]:
    """v1.95 Spine A AC1 (f015de6b3a18; Mike ruled 2026-09-05, f015e5ee0ede §RULED):
    the box ships no Studio manifest and no starter vault-entity record — genesis
    runs on the customer's machine at first boot. ORDERING IS LOAD-BEARING: this
    reads the box's vault/00-index.jsonl, which the final purge deletes, so it
    must run before that purge or clause 2 passes vacuously."""
    import json
    box = Path(build_dir)
    offenders: List[str] = []
    manifest = box / ".tropo" / "studio-identity.md"
    if manifest.exists():
        offenders.append(
            ".tropo/studio-identity.md is present in the box (a shipped Studio "
            "manifest — every customer would inherit this same studio_id)"
        )
    index_path = box / "vault" / "00-index.jsonl"
    if index_path.is_file():
        with index_path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("type") == "entity" and record.get("subtype") == "vault-entity":
                    offenders.append(
                        "vault/00-index.jsonl line %d carries a type: entity / subtype: "
                        "vault-entity record (uid=%s, path=%s) — a shipped starter pair"
                        % (lineno, record.get("uid") or "?", record.get("path") or "?")
                    )
    return offenders


def shadow_substitution_problems(build_dir, pairs) -> "tuple[List[str], List[str]]":
    """Both halves of every SHADOW pair, checked against the built box.

    `pairs` is resolver.shadow_pairs(): (source_path, twin_designation). A
    substitution is two claims — twin present AND source absent — and checking
    only one is how an unwired pair passes. Returns (problems, confirmations)."""
    box = Path(build_dir)
    problems: List[str] = []
    confirmed: List[str] = []
    for source_path, twin in pairs:
        source_in_box = (box / source_path).exists()
        twin_in_box, twin_at = False, None
        if twin:
            files_dir = box / "vault" / "files"
            if files_dir.is_dir():
                for fname in os.listdir(files_dir):
                    if str(twin) in fname:
                        twin_in_box, twin_at = True, os.path.join("vault/files", fname)
                        break
        if source_in_box:
            problems.append(
                "SHADOW violated: source %s IS in the box; the twin was meant to ship "
                "in its place" % source_path
            )
        if twin and not twin_in_box:
            problems.append(
                "SHADOW incomplete: %s is designated to twin %s, which is NOT in the "
                "box — the source was withheld and nothing replaced it, which is a "
                "hole, not a substitution" % (source_path, twin)
            )
        if not source_in_box and twin_in_box:
            confirmed.append("SHADOW %s → %s" % (source_path, twin_at))
    return problems, confirmed


# ── The subprocess gates (Steps 10.5, 10.5a, 10.7) ───────────────────────────
# Each runs the same command the build ran directly and returns problems; the
# captured output rides along as the second element so a Gate can carry it as
# evidence and the build can print it, one definition, two readers.

def _run(cmd, cwd, timeout, env=None):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd),
                          timeout=timeout, env=env)


def release_harness_problems(studio_root, build_dir) -> "tuple[List[str], str]":
    """Step 10.5 (brief f13cc214, Mike-A115 2026-06-17): the box passes its own
    mechanical regression harness. An absent harness was a silent SKIP in the
    build; here it is a problem, because a gate that cannot run must not read
    as pass at the seal."""
    harness = Path(studio_root) / ".tropo" / "scripts" / "test-harness-check.py"
    if not harness.is_file():
        return (["test-harness-check.py not found at %s — the regression gate could not "
                 "run (do not treat as pass)" % harness], "")
    try:
        result = _run(["python3", str(harness), "--release-dir", str(build_dir)],
                      cwd=studio_root, timeout=120)
    except Exception as exc:  # noqa: BLE001 — TimeoutExpired and friends
        return (["test-harness timed out or could not run: %s: %s"
                 % (type(exc).__name__, exc)], "")
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return (["release failed its own test-harness regression (exit %d); see "
                 "test-report.md in the box" % result.returncode], out)
    return ([], out)


#: The status line tropo-test.py prints for a Studio that has not derived its
#: index yet. Read as TEXT, never as an exit code — see the note in
#: box_self_test_problems. Kept in sync by the test that asserts the shipped
#: tool still emits it.
_NOT_INITIALIZED_STATUS = "STATUS: NOT INITIALIZED"


SCORE_FORMULA_DOCTRINE_REL = os.path.join(".tropo-studio", "score-formula-doctrine.md")


def score_formula_doctrine_problems(build_dir) -> "tuple[List[str], str]":
    """The shipped memory curator reads .tropo-studio/score-formula-doctrine.md at
    boot. Assert the box actually carries it.

    THIS GUARD IS THE POINT, not the placement step it protects. The file was
    declared as a ship-artifact, read by the build, reported as copied, and still
    absent from every box for six releases — because a later step wiped the folder
    it had been copied into. A placement alone restores that state exactly: it
    works today and the next person to reorder those steps breaks it again with
    every gate green, which is how it lasted six releases the first time.

    Content is checked, not just presence. An empty or placeholder file would
    satisfy a bare existence test while giving the curator nothing to rank with.
    """
    box = Path(build_dir)
    doctrine = box / SCORE_FORMULA_DOCTRINE_REL
    if not doctrine.is_file():
        return ([
            "the box does not carry %s — the shipped memory curator (50c0bdce) "
            "reads it at boot and cannot rank memory without it. If a build step "
            "was recently reordered, check that the placement still runs AFTER "
            "step_7_create_vault_skeleton, which rmtree's that folder "
            "(ship-artifact f0155122c0b8)." % SCORE_FORMULA_DOCTRINE_REL], "")
    try:
        body = doctrine.read_text(encoding="utf-8")
    except OSError as exc:
        return (["%s is present but unreadable: %s"
                 % (SCORE_FORMULA_DOCTRINE_REL, exc)], "")
    problems = []
    if len(body.strip()) < 200:
        problems.append(
            "%s is present but only %d bytes — a placeholder satisfies a presence "
            "check and gives the curator nothing to rank with"
            % (SCORE_FORMULA_DOCTRINE_REL, len(body.strip())))
    if "<FILL" in body:
        problems.append(
            "%s still contains <FILL …> placeholders; the doctrine ships as-is, "
            "it is not a template" % SCORE_FORMULA_DOCTRINE_REL)
    return (problems, body[:400])


def box_self_test_problems(build_dir) -> "tuple[List[str], str]":
    """Step 10.5a (v1.80 S2, dev-spec be1979b6): the shipped self-test passes
    INSIDE the box.

    THIS GATE JUDGED ONE INTEGER AND READ NOTHING ELSE (f0152b4c4ef4, cured
    2026-09-08 by talos-t65 under argus-a175's direction). The whole of its
    verdict was `if result.returncode >= 2`, while the captured output was
    carried into evidence no consumer ever reads back. Measured consequence: an
    exit 0 whose stdout literally contained "RED" and "ERROR: validator
    subprocess failed" returned problems=[] and PASSED. The gate built to catch
    a dishonest self-test could not see the dishonest case at all.

    Three things changed, and the third is the one that matters most:

    1. The gate reads the OUTPUT, not only the code. A run that produced no
       health verdict is a refusal whatever it exited with.
    2. NOT INITIALIZED is recognised as its own state, by its status LINE. That
       is deliberate: the stranger-facing exit code for that state is decision 4
       on the v1.96 board and is Mike's to settle. Because this gate keys on
       text, his answer changes nothing here — which is the point. Do not
       reintroduce an exit-code test for this state.
    3. The box under test is NOT the box that ships (see
       box_self_test_on_initialized_copy). A box ships without its index by
       design, so running the self-test on the shipped bytes asks it a question
       it cannot answer.
    """
    box_test = Path(build_dir) / "vault" / "tools" / "tropo-test.py"
    if not box_test.is_file():
        return (["tropo-test.py not found in the built box at %s — the shipped test "
                 "surface must be present" % box_test], "")
    try:
        # --no-auto-init, and an honest note about why (talos-t66, 2026-09-08).
        # AT RUNTIME TODAY THIS FLAG CHANGES NOTHING, and the first version of
        # this comment claimed the opposite. box_self_test_problems has exactly
        # one production caller — box_self_test_on_initialized_copy, which has
        # already rebuilt the copy with --apply — so the not-initialized branch
        # is unreachable in production and auto-init could never fire. Corrected
        # in adversarial review rather than left as a confident wrong sentence.
        #
        # It stays because this is a public library entry point and the reason
        # below is sound: tropo-test.py now builds the index when the validator says
        # the Studio has none — Mike's ruling, and right for a human who typed
        # `npm test`. A gate must never take that path: it would write an index
        # into the very box this gate is sealing, and the same extracted_tree is
        # read by build-no-studio-identity, which flips PASS -> REFUSED the moment
        # a genesis artifact appears (the reason --no-genesis is load-bearing in
        # box_self_test_on_initialized_copy above). It would also destroy THIS
        # gate's own wrong-box detection: the NOT INITIALIZED branch below is how
        # it knows it is being pointed at shipped bytes instead of an initialized
        # copy, and an auto-initializing self-test can never answer that.
        # Argus A175 on the record (f0152b4c4ef4): "Do not silently initialize a
        # customer's live Studio as a diagnostic side effect."
        result = _run(["python3", str(box_test), "--quick", "--no-auto-init"],
                      cwd=build_dir, timeout=300)
    except Exception as exc:  # noqa: BLE001
        return (["shipped self-test timed out or could not run: %s: %s"
                 % (type(exc).__name__, exc)], "")
    out = (result.stdout or "") + (result.stderr or "")

    # NOT INITIALIZED — read as text, never as a code. On an un-indexed box this
    # is the correct and expected answer, and it is not a health verdict, so the
    # gate must not accept it as one.
    if _NOT_INITIALIZED_STATUS in out:
        return (["shipped self-test reports NOT INITIALIZED — no health verdict was "
                 "produced. The box has no index by design; this gate must run "
                 "against an initialized disposable copy, not the shipped bytes."], out)

    # NO VERDICT — the case that used to pass silently. A validator that aborted
    # before printing its Summary now says so; anything claiming health without
    # having examined something is refused here rather than recorded as green.
    if "NO HEALTH VERDICT HAS BEEN PRODUCED" in out:
        return (["shipped self-test produced NO health verdict (exit %d) — the "
                 "validator aborted before finishing. A pass having examined "
                 "nothing is the failure this gate exists to catch."
                 % result.returncode], out)

    if result.returncode >= 2:
        return (["shipped self-test (tropo-test.py) FAILED RED inside the box "
                 "(exit %d)" % result.returncode], out)
    return ([], out)


def box_self_test_on_initialized_copy(build_dir) -> "tuple[List[str], str]":
    """The same self-test, on a DISPOSABLE INITIALIZED COPY. The artifact is not touched.

    Argus A175's direction (f0152b4c4ef4): "For the build gate, evaluate an
    initialized disposable copy with the existing rebuilder and then the real
    self-test; keep the artifact pristine. Do not silently initialize a
    customer's live Studio as a diagnostic side effect."

    Why a copy and not the box: a release box ships without its index and derives
    it on first use, so the shipped bytes can only ever answer NOT INITIALIZED.
    Initializing the box in place would both mutate the artifact and — measured —
    arm a different gate: `build-no-studio-identity` reads the SAME extracted_tree
    and would flip PASS -> REFUSED, because genesis mints .tropo/studio-identity.md
    and a vault-entity starter pair.

    `--no-genesis` is therefore load-bearing, not cosmetic. It is also what the
    release build itself passes when it rebuilds the box's own index, so this copy
    is initialized the way the build does it, not the way a customer does.

    Measured cost on Python 3.9.6: copy 0.68s, rebuild 5.28s (26 MB -> 34 MB),
    ~19s added to the phase in total, of which ~13s is this gate finally doing
    real work.
    """
    import shutil
    import tempfile

    box = Path(build_dir)
    rebuilder = box / "vault" / "tools" / "tropo-rebuild-index.py"
    if not rebuilder.is_file():
        return (["tropo-rebuild-index.py not found in the built box at %s — the box "
                 "cannot derive its own index, so a customer's first use cannot "
                 "succeed either" % rebuilder], "")

    # A fresh mkdtemp whose ONLY child is the copy. Deliberate: sibling
    # directories are part of some checks' input surface (f01586b60487), so an
    # isolated parent keeps this gate's result about the box and nothing else.
    tmp_parent = tempfile.mkdtemp(prefix="tropo-box-selftest-")
    copy = Path(tmp_parent) / "box"
    try:
        shutil.copytree(box, copy, symlinks=True)
        init = _run(["python3", str(copy / "vault" / "tools" / "tropo-rebuild-index.py"),
                     "--apply", "--no-genesis", "--vault-path", str(copy)],
                    cwd=str(copy), timeout=600)
        if init.returncode != 0:
            return (["the box could not derive its own index (exit %d) — a customer "
                     "running the one command the box tells them to run would fail "
                     "here" % init.returncode],
                    (init.stdout or "") + (init.stderr or ""))
        problems, out = box_self_test_problems(copy)
        return (problems, out)
    except Exception as exc:  # noqa: BLE001
        return (["initialized-copy self-test could not run: %s: %s"
                 % (type(exc).__name__, exc)], "")
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)


def box_registry_rows_problems(build_dir) -> "tuple[List[str], str]":
    """Step 10.5a's second half: registry-row regeneration landed in the box
    (read the box, not the call). An absent registry file stays non-blocking,
    as it was at v1.80; an EMPTY one refuses."""
    box = Path(build_dir)
    registry = box / "vault" / ".tropo-studio" / "registries" / "subsystem-registry.jsonl"
    if not registry.exists():
        registry = box / ".tropo-studio" / "registries" / "subsystem-registry.jsonl"
    if not registry.exists():
        return ([], "subsystem-registry.jsonl not found in box at %s — registry-row "
                    "verification skipped (non-blocking at v1.80)" % registry)
    rows = [l for l in registry.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        return (["subsystem-registry.jsonl in the built box has 0 rows — regeneration "
                 "did not land; the box is incomplete (S2)"], "")
    return ([], "subsystem-registry.jsonl: %d row(s) in box — regeneration confirmed"
            % len(rows))


def covenant_floor_problems(studio_root) -> "tuple[List[str], str]":
    """Step 10.7 (ADR-049 layer 2; dev-spec fc4874f4, Mike 2026-07-01): THE FLOOR
    TEST — the update path touches no user file. Reads only the source tree, so
    the registry computes it to lock-static: it now speaks before a build is
    attempted, which is the compiler-loop point. Two runs: the gauntlet (a
    planted violation must be caught, or the gate is not trustworthy) and the
    real run."""
    floor_test = Path(studio_root) / "vault" / "tools" / "tests" / "test_clean_update_floor.py"
    if not floor_test.is_file():
        return (["floor test not found at %s — the covenant gate cannot be skipped by "
                 "absence" % floor_test], "")
    outputs: List[str] = []
    try:
        gauntlet = _run(["python3", str(floor_test), "--gauntlet"], cwd=studio_root, timeout=60)
        outputs.append(gauntlet.stdout or "")
        if gauntlet.returncode != 0:
            return (["the covenant gate failed its own gauntlet (a planted violation was "
                     "NOT detected); fix test_clean_update_floor.py before shipping"],
                    "\n".join(outputs))
        real = _run(["python3", str(floor_test)], cwd=studio_root, timeout=60)
        outputs.append(real.stdout or "")
        if real.returncode != 0:
            return (["THE FLOOR TEST failed: the update path would touch user files "
                     "(ADR-049 covenant)"], "\n".join(outputs))
    except Exception as exc:  # noqa: BLE001
        return (["covenant gate timed out or could not run: %s: %s"
                 % (type(exc).__name__, exc)], "\n".join(outputs))
    return ([], "\n".join(outputs))


def git_tree_commit(root) -> str:
    """The HEAD the tree at `root` is checked out at, or '' when not a git tree.
    Spine B AC2/AC3: every evidence row names the commit the phase ran against."""
    try:
        result = _run(["git", "-C", str(root), "rev-parse", "HEAD"], cwd=root, timeout=10)
    except Exception:  # noqa: BLE001
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


# ── The tree-side guards (lock-static) ───────────────────────────────────────

def _read_version_stamp(path: Path) -> str:
    """The build tool's read_current_version, verbatim in effect: the semver in
    a version.md's frontmatter, else the first semver anywhere, else 0.0.0."""
    text = path.read_text(errors="replace")
    m = re.search(r"version:\s*[\"']?(\d+\.\d+\.\d+)", text) or re.search(r"(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else "0.0.0"


def overwrite_problems(version, releases_dir, force=False) -> List[str]:
    """The V36 2026-04-30 scenario (vela-v37, task 87e3b4d6): a stale source
    version.md computes a wrong new_version; the output dirs already exist
    with prior real content; a blind rmtree destroys it. Before any write,
    each existing target must carry a version.md that agrees with `version`.
    `force` is the deliberate-overwrite case (the build's --force flag,
    passed through context — the gate honours it, the gate has no flag)."""
    product = "tropo-os-v%s" % version
    problems: List[str] = []
    for label, target in (("build", Path(releases_dir) / ("v%s" % version) / "builds" / product),
                          ("testing", Path(releases_dir) / ("v%s" % version) / "testing" / product)):
        if not target.exists():
            continue
        stamp = None
        for candidate in (target / ".tropo" / "version.md", target / "version.md"):
            if candidate.exists():
                stamp = _read_version_stamp(candidate)
                break
        if stamp is None:
            if force:
                continue
            problems.append(
                "%s dir %s exists but carries no version.md stamp — cannot verify "
                "content-version agreement; an unidentifiable tree would be handed to "
                "an unconditional rmtree (re-run with --force if intended; else inspect, "
                "move or archive it)" % (label, target))
        elif stamp != str(version):
            if force:
                continue
            problems.append(
                "%s dir %s has version.md = %s but the build target is %s — overwriting "
                "would clobber %s working content (the V36 scenario); update source "
                ".tropo/version.md if stale, or --force to overwrite deliberately"
                % (label, target, stamp, version, stamp))
    return problems


def absolute_path_problems(source_tree, strict=False) -> List[str]:
    """v1.90 shipped one paste from public with three maintainer scripts hard-coded
    to one machine, and the box's own test-report certified their absence. The
    validator that catches it (tropo-validate-no-absolute-paths.py, c9b7d4e2)
    existed with zero call sites; harness check 6b later wired it over the BOX.
    This is the same scan over the SHIPPED TOOL CORPUS of the source tree
    (vault/tools, .tropo/scripts), at lock-static, so the leak is named before a
    build is attempted. Uses the tool's own walk, allowlist and patterns — one
    definition."""
    import importlib.util
    tool = Path(source_tree) / "vault" / "tools" / "tropo-validate-no-absolute-paths.py"
    if not tool.is_file():
        # The instrument lives with the tools; a tree without it cannot be scanned
        # by it. Reported, never silently green.
        return ["%s is absent — the absolute-path scan could not run" % tool]
    spec = importlib.util.spec_from_file_location("_tropo_no_abs_paths_for_gate", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    problems: List[str] = []
    root = Path(source_tree)
    # SCOPE: the tool corpus that ships wholesale — vault/tools/ and
    # .tropo/scripts/ — not the whole studio. The whole studio carries the
    # recycle bin, the per-machine index and release notes, none of which ship;
    # scanning them at lock-static drowned the signal in 50 hits on the first
    # real run (2026-09-05). The BOX-wide scan stays where it is, in harness
    # check 6b at the candidate phase. This gate is the v1.90 leak class
    # exactly: a maintainer script in the shipped tool corpus hard-coded to
    # one machine.
    corpus = [root / "vault" / "tools", root / ".tropo" / "scripts"]
    for base in corpus:
        if not base.is_dir():
            continue
        for path in module.walk_files(base):
            if module.is_allowlisted(path, strict):
                continue
            for lineno, name, excerpt in module.scan_file(path):
                problems.append("%s:%d [%s] %s" % (path.relative_to(root).as_posix(), lineno, name, excerpt))
                if len(problems) >= 50:
                    problems.append("… (scan stopped at 50 hits)")
                    return problems
    return problems


def activation_key_problems(studio_root, activation_uid, target_version) -> "tuple[List[str], str]":
    """The Pipeline Activation Key (dev-spec 2ffdd9d6): a box built standalone is
    indistinguishable from a pipeline-produced one and is believed to have
    passed gates that never ran. Verifies the key minted at the
    produce-release-folder gate; the attested-build fallback (argus-a129 spec,
    Mike 2026-07-11) is the SEPARATE, narrower source for this gate only.
    Reads .tropo/scripts/lib/release_authorization.py by path (it roots itself
    from its own location, so `studio_root` names which tree's lib runs)."""
    import importlib.util
    lib = Path(studio_root) / ".tropo" / "scripts" / "lib" / "release_authorization.py"
    if not lib.is_file():
        return (["%s is absent — the activation key cannot be verified" % lib], "")
    spec = importlib.util.spec_from_file_location("_tropo_release_authorization_for_gate", lib)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        key = module.require_release_authorization(activation_uid, "produce-release-folder")
        return ([], "Pipeline Activation Key verified (activation %s, fingerprint %s…)"
                % (activation_uid, str(key.get("fingerprint", ""))[:12]))
    except module.ReleaseAuthorizationError as exc:
        key_error = str(exc)
    attested = None
    if target_version:
        try:
            attested = module.attested_build_authorization(str(target_version))
        except module.ReleaseAuthorizationError:
            attested = None
    if attested:
        return ([], "Attested-Build Authorization verified (release %s, version %s, attestation %s)"
                % (attested.get("release_uid"), attested.get("version"), attested.get("attestation_uid")))
    return (["no valid Pipeline Activation Key: %s — a release is produced through the "
             "pipeline runtime, which mints the key at the produce-release-folder gate; "
             "do not invoke the build standalone (no key, no build)" % key_error], "")


# ── Spine A AC7: the reachability rows, as candidate-phase checks over the box ──
# Declared by f015de6b3a18 AC7, registered and executed through the same registry
# as every other box guard (f015997f8d8e AC1/AC4). Each cannot pass on an empty
# box: an absent instruction corpus, changelog or memory surface is a problem,
# never a vacuous pass.

CONCIERGE_INSTRUCTION_GLOBS = (".tropo/concierge/*.md", ".tropo/playbooks/concierge-paths/*.md",
                               "START-TROPO.md", "README.md")


def _doc_currency_module(source_tree):
    import importlib.util
    tool = Path(source_tree) / "vault" / "tools" / "tropo-check-doc-currency.py"
    if not tool.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_tropo_doc_currency_for_gate", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def doc_currency_problems(source_tree, build_dir) -> List[str]:
    """AC7 row (a): every path a shipped instruction document names resolves
    INSIDE the box. Runs tropo-check-doc-currency's own scan (one definition)
    over the assembled box; a dead INSTRUCTION reference is a problem, retired
    notices and prose are not. An empty box has no instruction files, which is
    itself the problem — the row cannot pass on nothing."""
    module = _doc_currency_module(source_tree)
    if module is None:
        return ["tropo-check-doc-currency.py is absent from the source tree — the reachability scan could not run"]
    box = module.Box(Path(build_dir))
    files = list(box.instruction_files(module.DEFAULT_GLOBS))
    if not files:
        return ["no shipped instruction files under %s — nothing to check is not a pass" % ", ".join(module.DEFAULT_GLOBS)]
    problems: List[str] = []
    # The uid arm (Spine B committed substrate, talos-t62 e7c716dd2): a uid a
    # shipped instruction names is a reference a reader follows exactly as a
    # path is. It is decidable only against the SOURCE Studio's governed set --
    # git shas are hex too -- so the gate passes source_tree's index, the one
    # argument the tool's own main() passes and this caller did not (argus-a172,
    # 2026-09-06: the arm was declared, the gate never reached it). An empty
    # governed set is not "nothing to check": it means the source has no index
    # here, and the row cannot pass on an arm that evaluated nothing.
    known_uids = set()
    if hasattr(module, "governed_uids") and hasattr(module, "scan_uids"):
        known_uids = module.governed_uids(Path(source_tree))
        if not known_uids:
            problems.append("uid arm evaluated nothing: %s carries no vault/00-index.jsonl, "
                            "so no token can be classified a governed uid" % source_tree)
    for rel in files:
        try:
            text = box.read(rel)
        except Exception:  # noqa: BLE001
            continue
        for lineno, ref, form in module.scan_text(text):
            if form != module.INSTRUCTION or box.exists(ref, relative_to=rel):
                continue
            # The tool's own skip, one definition (talos-t63, 2026-09-06): the
            # index family AND the per-studio boot derivations the build
            # excludes, matched on the normalised box path. This loop carried
            # its own raw `ref in GENERATED_AT_BOOT` copy -- a second reader --
            # and refused v1.95 candidate #1 on a link the kernel pointer tells
            # every reader to expect absent.
            skip = getattr(module, "is_generated_at_boot", None)
            if (skip(ref, rel) if skip else ref in module.GENERATED_AT_BOOT):
                continue
            where = box.locate_elsewhere(ref)
            problems.append("%s:%d names %s — %s" % (rel, lineno, ref,
                            ("ships at %s (misrouted)" % where) if where else "absent from the box"))
        if known_uids:
            for lineno, uid, form in module.scan_uids(text, known_uids):
                if form != module.INSTRUCTION or box.has_uid(uid):
                    continue
                problems.append("%s:%d names %s — governed by the source, absent from the box" % (rel, lineno, uid))
    return problems


_SHELL_AS_PROSE_RE = re.compile(r"`(?:open|xdg-open|start)\s+[^`]*`|hand (?:them|the user) the one command")


def shell_instruction_problems(build_dir) -> List[str]:
    """AC7 row (b), Mike-ruled 2026-09-05: no shipped concierge instruction is a
    bare platform-specific shell command presented as prose — Po renders a
    clickable link, else an absolute path, never `open <path>`. Scans the
    concierge corpus in the box; changelog sections are history and skipped."""
    box = Path(build_dir)
    files = []
    for pattern in CONCIERGE_INSTRUCTION_GLOBS:
        files.extend(sorted(box.glob(pattern)))
    if not files:
        return ["no concierge instruction files in the box (%s) — nothing to check is not a pass"
                % ", ".join(CONCIERGE_INSTRUCTION_GLOBS)]
    problems: List[str] = []
    for path in files:
        text = path.read_text(errors="replace")
        live = text.split("## Changelog")[0]
        for lineno, line in enumerate(live.splitlines(), 1):
            if _SHELL_AS_PROSE_RE.search(line):
                problems.append("%s:%d presents a shell command as the instruction: %s"
                                % (path.relative_to(box).as_posix(), lineno, line.strip()[:120]))
    return problems


def changelog_names_version_problems(build_dir, version) -> List[str]:
    """AC7 row (c): the shipped CHANGELOG.md names the version being shipped
    (`## [X.Y.Z]`). The Metis G83 anti-drift gate's shape, over the box."""
    changelog = Path(build_dir) / "CHANGELOG.md"
    if not changelog.is_file():
        return ["CHANGELOG.md is absent from the box"]
    text = changelog.read_text(errors="replace")
    if not re.search(r"^## \[%s\]" % re.escape(str(version)), text, re.M):
        return ["CHANGELOG.md in the box carries no `## [%s]` entry for the version shipped" % version]
    return []


MEMORY_SURFACES = (
    (".tropo-studio/operating-principles.md", "## 14. Memory Writes"),
    ("CLAUDE.md", "## Memory Writes Go to Tropo Memory"),
)


def memory_surfaces_problems(build_dir) -> List[str]:
    """AC7 row (i) / AC6's completeness gate: every boot-routed memory-sovereignty
    surface tropo-memory.capsule.md names (OP-14 in the shipped principles;
    CLAUDE.md §Memory Writes) is present in the box AND carries the rule."""
    box = Path(build_dir)
    problems: List[str] = []
    for rel, marker in MEMORY_SURFACES:
        path = box / rel
        if not path.is_file():
            problems.append("%s is absent from the box" % rel)
        elif marker not in path.read_text(errors="replace"):
            problems.append("%s ships without %r — the memory-sovereignty rule is not on it" % (rel, marker))
    return problems
