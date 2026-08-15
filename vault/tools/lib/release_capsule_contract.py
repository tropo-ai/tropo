#!/usr/bin/env python3
"""Executable release-plan / build / release predicates (dev-spec a54b9889).

The capsules describe these rules; this module is what refuses. Prose-only
correction is a FAIL by the spec's own terms, because a rule nothing enforces is
a rule the next cycle discovers by shipping.

Three rules move here together, since they are one chain:

  C1  A v1.87+ release-plan's authority is its LOCKED ORDERED FAN-IN, not a
      singular `basis_spec`. `basis_spec` becomes optional legacy frontmatter,
      and plans that carry it keep their old check.
  C2  A v1.87+ release-engineering build derives from its locked release-plan,
      whose fan-in binds the done specs. Legacy `basis_spec` derivation stays
      grandfathered as a branch, never as a fallback for a new plan.
  C3  For v1.87+, a release record is invalid until all four live Verify
      instruments have exactly one accepted receipt each against ONE frozen
      `package_sha256`. Releases predating the release-pipeline keep the
      historical f4a8c2d6 gauntlet as their contract.

Every function returns a LIST OF PROBLEMS rather than a boolean. A caller that
gets `False` can only say "invalid"; the operator's next move differs completely
between "this plan has no fan-in yet" and "this plan's version does not match
the build", and a predicate that cannot tell them apart pushes that diagnosis
onto whoever is holding the failure at the time.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

#: The release whose plan first carries fan-in rather than a basis_spec.
FAN_IN_ERA = (1, 87, 0)

#: What a v1.87+ locked plan must carry. These are the fields the release lock
#: itself authors, so requiring them is requiring that the lock actually ran —
#: not that someone typed the right words into frontmatter.
FAN_IN_FIELDS = (
    "dev_spec_uids",
    "fan_in_manifest_ref",
    "fan_in_digest",
    "release_activation_uid",
    "release_pipeline_run_uid",
)

LOCKED_STATUSES = frozenset({"locked"})


def parse_version(value) -> Optional[tuple]:
    """`1.87.0` → `(1, 87, 0)`; anything unparseable → None.

    None is returned rather than a zero tuple: an unreadable version is an
    unknown, and treating it as 0.0.0 would silently route a malformed plan into
    the legacy branch, which is the most permissive one.
    """
    text = str(value or "").strip().lstrip("v")
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except (TypeError, ValueError):
        return None


def in_fan_in_era(version) -> bool:
    parsed = parse_version(version)
    return bool(parsed and parsed >= FAN_IN_ERA)


def _is_locked(entry: dict) -> bool:
    """Locked by status, or by the locked_by/locked_at pair.

    design-spec's canonical lock signal is the pair, not a status field — the
    v2.2 compound-lock amendment exists because a strict `status: locked` read
    failed well-formed locked specs like f3c7a291.
    """
    if str(entry.get("status") or "").strip().lower() in LOCKED_STATUSES:
        return True
    return bool(entry.get("locked_by")) and bool(entry.get("locked_at"))


def check_release_plan(plan: dict, resolve: Optional[Callable] = None) -> list:
    """Is this release-plan's authority real?

    `resolve(uid) -> entry|None` is injected so the legacy branch can check a
    basis_spec without this module owning a vault reader. A caller that does not
    supply one is not asking for the legacy check to be skipped — a legacy plan
    with no resolver reports that it could not be verified.
    """
    problems: list = []
    if str(plan.get("type") or "") != "release-plan":
        problems.append(f"{plan.get('uid')} is type {plan.get('type')!r}, not a release-plan")
        return problems

    if not _is_locked(plan):
        # Only locked plans make claims worth checking. An in-flight plan is
        # allowed to be incomplete; that is what `specify` means.
        return problems

    if in_fan_in_era(plan.get("release_version")):
        for field in FAN_IN_FIELDS:
            value = plan.get(field)
            if not value:
                problems.append(
                    f"locked v1.87+ plan {plan.get('uid')} carries no {field}; its "
                    "ignition authority is the ordered receipt-bound fan-in the "
                    "release lock writes, so a plan missing it is locked over nothing"
                )
        return problems

    basis = plan.get("basis_spec")
    if not basis:
        problems.append(
            f"pre-v1.87 plan {plan.get('uid')} carries neither basis_spec nor "
            "fan-in, so nothing grounds it"
        )
        return problems
    if resolve is None:
        problems.append(
            f"plan {plan.get('uid')} carries legacy basis_spec {basis} but no "
            "resolver was supplied, so its lock state could not be verified"
        )
        return problems
    spec = resolve(str(basis)) or {}
    if str(spec.get("type") or "") != "design-spec":
        problems.append(
            f"basis_spec {basis} is type {spec.get('type')!r}, not a design-spec")
    elif not _is_locked(spec):
        problems.append(f"basis_spec {basis} is not locked")
    return problems


def check_build_derivation(build: dict, plan: dict,
                           resolve: Optional[Callable] = None) -> list:
    """May this release-engineering build derive from this release-plan?

    The v1.87 branch and the legacy branch are selected by the PLAN's era, not
    by whichever one happens to pass. Falling back to legacy when the fan-in
    check fails would make compatibility an escape hatch: a new plan with no
    fan-in would qualify through a rule written for plans that predate fan-in.
    """
    problems: list = []
    derived = [str(u) for u in (build.get("derived_from") or [])]
    if not derived:
        problems.append(f"build {build.get('uid')} has empty derived_from")

    if not _is_locked(plan):
        problems.append(
            f"release-plan {plan.get('uid')} is status {plan.get('status')!r}, not "
            "locked; a build cannot derive authority from a plan that can still change"
        )

    build_version = parse_version(build.get("build_version"))
    plan_version = parse_version(plan.get("release_version"))
    if not build_version or build_version != plan_version:
        problems.append(
            f"build_version {build.get('build_version')!r} does not match plan "
            f"release_version {plan.get('release_version')!r}"
        )

    streams = {str(u) for u in (plan.get("streams") or [])}
    member_of = {str(u) for u in (build.get("member_of") or [])}
    if not streams & member_of:
        problems.append(
            f"no project-scope overlap: build {build.get('uid')} member_of "
            f"{sorted(member_of)} shares nothing with plan streams {sorted(streams)}, "
            "so this build was authored outside the plan it claims"
        )

    if in_fan_in_era(plan.get("release_version")):
        if str(plan.get("uid")) not in derived:
            problems.append(
                f"build {build.get('uid')} does not name its release-plan "
                f"{plan.get('uid')} in derived_from; for v1.87+ the plan IS the "
                "derivation, because its fan-in is what binds the done specs"
            )
        if not plan.get("dev_spec_uids") or not plan.get("fan_in_digest"):
            problems.append(
                f"release-plan {plan.get('uid')} has no verified fan-in "
                "(dev_spec_uids + fan_in_digest), so there is no locked-spec "
                "authority for this build to inherit"
            )
        return problems

    basis = str(plan.get("basis_spec") or "")
    if not basis:
        problems.append(
            f"legacy plan {plan.get('uid')} carries no basis_spec to derive from")
        return problems
    if basis not in derived:
        problems.append(
            f"build {build.get('uid')} does not include the plan's basis_spec "
            f"{basis} in derived_from")
    spec = (resolve(basis) if resolve else None) or {}
    if not spec:
        problems.append(f"basis_spec {basis} did not resolve")
    elif str(spec.get("type") or "") != "design-spec" or not _is_locked(spec):
        problems.append(f"basis_spec {basis} is not a locked design-spec")
    return problems


def _load_entries(vault, wanted_type: str) -> list:
    """Every governed instance of one type, with frontmatter, from the index.

    Reads through the same index surfaces every other check-family uses, so a
    UID this cannot see is a UID the rest of the validator cannot see either.
    """
    from pathlib import Path  # noqa: PLC0415

    from lib import index_surfaces  # noqa: PLC0415

    vault = Path(vault)
    out = []
    for record in index_surfaces.load_index_records(vault, include_archive=False):
        if record.get("type") != wanted_type:
            continue
        uid = str(record.get("uid") or "")
        path = _instance_path(vault, uid)
        if path is None:
            continue
        fm = _read_frontmatter(path)
        if fm:
            out.append((uid, fm))
    return out


def _instance_path(vault, uid: str):
    from pathlib import Path  # noqa: PLC0415

    for folder in ("files", "capsules", "playbooks", "skills", "tools"):
        candidate = Path(vault) / "vault" / folder / f"{uid}.md"
        if candidate.is_file():
            return candidate
    return None


def _read_frontmatter(path) -> dict:
    import yaml  # noqa: PLC0415

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        loaded = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def run_all_release_plan_checks(vault) -> tuple:
    """check-one / validator entry point for `type: release-plan`.

    Registered in the production dispatcher so `tropo-check-one.py <plan-uid>`
    actually runs C1. Before this, the predicate existed and only its own tests
    called it, which is a rule that cannot refuse anything (Argus, evt 110).
    """
    entries = _load_entries(vault, "release-plan")
    resolver = _vault_resolver(vault)
    findings = []
    for uid, fm in entries:
        fm = dict(fm)
        fm.setdefault("uid", uid)
        fm.setdefault("type", "release-plan")
        for problem in check_release_plan(fm, resolve=resolver):
            findings.append(f"[FAIL] {uid} (release-plan): {problem}")
    return findings, len(entries), len(findings)


def run_all_build_checks(vault) -> tuple:
    """check-one / validator entry point for `type: build` (C2).

    A build is only judged when its release-plan can be identified: derivation
    is a claim ABOUT a plan, and a build naming none is a different finding that
    build.capsule's own family owns.
    """
    entries = _load_entries(vault, "build")
    plans = {uid: fm for uid, fm in _load_entries(vault, "release-plan")}
    resolver = _vault_resolver(vault)
    findings = []
    checked = 0
    for uid, fm in entries:
        fm = dict(fm)
        fm.setdefault("uid", uid)
        plan = _plan_for_build(fm, plans)
        if plan is None:
            continue
        checked += 1
        for problem in check_build_derivation(fm, plan, resolve=resolver):
            findings.append(f"[FAIL] {uid} (build): {problem}")
    return findings, checked, len(findings)


def _plan_for_build(build: dict, plans: dict) -> Optional[dict]:
    derived = {str(u) for u in (build.get("derived_from") or [])}
    for uid, fm in plans.items():
        if uid in derived:
            return dict(fm, uid=uid)
    version = parse_version(build.get("build_version"))
    if not version:
        return None
    for uid, fm in plans.items():
        if parse_version(fm.get("release_version")) == version:
            return dict(fm, uid=uid)
    return None


def _vault_resolver(vault) -> Callable:
    def resolve(uid: str):
        path = _instance_path(vault, str(uid))
        return _read_frontmatter(path) if path else None
    return resolve


def check_rule_10(release: dict, receipts: Iterable[dict]) -> list:
    """Four live Verify receipts over one frozen package, for v1.87+.

    Delegates the counting to `lib.release_verify`, which is the same code the
    publish gate calls. A second implementation here would be a second opinion,
    and the whole point of Rule 10 naming the live instruments is that there is
    one.
    """
    problems: list = []
    if not in_fan_in_era(release.get("release_version")):
        # Historical releases are judged by the contract that existed when they
        # shipped. Retro-applying a gate they could not have satisfied would
        # invalidate the archive rather than describe it.
        return problems

    digest = str(release.get("package_sha256") or "")
    run_uid = str(release.get("release_pipeline_run_uid") or "")
    if not digest:
        problems.append(
            f"release {release.get('uid')} names no package_sha256, so there is "
            "no frozen artefact for the receipts to be about")
    if not run_uid:
        problems.append(
            f"release {release.get('uid')} names no release_pipeline_run_uid, so "
            "receipts cannot be tied to the run that produced them")
    if problems:
        return problems

    from lib import release_verify  # noqa: PLC0415

    try:
        release_verify.assert_ready_to_publish(list(receipts), run_uid, digest)
    except release_verify.VerifyRefusal as refusal:
        problems.append(str(refusal))
    except Exception as unexpected:  # malformed receipt shapes surface here
        problems.append(f"receipt set could not be validated: {unexpected}")
    return problems
