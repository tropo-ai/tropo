#!/usr/bin/env python3
"""
---
uid: 0f3078fe
name: check-one
type: tool
title: check-one
description: "Targeted single-entry validator. Runs the capsule check-family for one vault entry (by UID) and exits 0 (PASS) or 1 (FAIL). The reusable primitive vc:true gate-step verification_commands call. Per CLI spec 2ddad3be (Argus A91 2026-05-31). Thin dispatcher over existing lib/*_validators.py factored check-families — no check reimplementation."
state: active
status: active
owner: talos
domain: "Targeted vault entry validation — exit-coded for verification_command use"
spawnable_by: []
transport: cli
implementation_kind: python-script
cli_command: "python3 vault/tools/tropo-check-one.py <uid> [--capsule <name>] [--vault-path <path>] [--quiet]"
script_path: vault/tools/tropo-check-one.py
created: 2026-06-01
created_by: talos-t11
governed_by: d5e1b4a3
member_of:
  - d6e50d38
refs:
  - 2ddad3be
schema_version: 2
extraction_scope: ship
---

EXIT CODES:
  0 — entry passes all checks in its type's check-family (zero defects)
  1 — entry has ≥1 defect
  2 — usage / resolution error

Per CLI spec at 2ddad3be. Uses the whole-vault dispatch approach (zero lib-touch).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[2]
LIB_DIR = VAULT_ROOT / ".tropo" / "scripts" / "lib"

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from lib import governed_path, index_surfaces, pruning_contract, template_leg  # noqa: E402 -- must follow the sys.path insert above

# Map entry type → lib module + function
DISPATCHER: dict[str, tuple[str, str]] = {
    "test-spec":   ("test_spec_validators",         "run_all_test_spec_checks"),
    "dev-spec":    ("dev_spec_validators",           "run_all_dev_spec_checks"),
    "doc-spec":    ("doc_spec_validators",           "run_all_doc_spec_checks"),
    "release":     ("release_validators",            "check_release_required_fields"),
    "action":      ("action_validators",             "run_all_action_checks"),
    "tool":        ("tool_validators",               "run_all_tool_checks"),
    "loop":        ("loop_validators",               "run_all_loop_checks"),
}


def resolve_type(uid: str, vault: Path) -> str | None:
    """Derive type across current + archive projections.

    ADR-047 removes history from the default retrieval surface, but targeted
    validation must still resolve an explicitly requested archived UID.
    """
    for rec in index_surfaces.load_index_records(vault, include_archive=True):
        if rec.get("uid") == uid:
            return rec.get("type")
    return None


def resolve_instance_path(uid: str, vault: Path) -> Path | None:
    """Resolve one governed instance across ADR-045 One-Home directories."""
    for rec in index_surfaces.load_index_records(vault, include_archive=True):
        if rec.get("uid") != uid:
            continue
        relative = rec.get("path")
        if relative:
            rel = template_leg._studio_relative_path(
                vault, relative, "indexed instance path"
            )
            candidate = vault / rel
            if candidate.exists() or candidate.is_symlink():
                return template_leg._strict_regular_file(
                    vault, rel, "indexed instance path"
                )

    # Governed Markdown homes resolve through the shared library, so a file
    # named <slug>-<uid>.md is found exactly like a bare <uid>.md one. It reads
    # directories, never the index — which matters here more than most places,
    # because check-one is what you reach for when the index is the thing you
    # doubt. Ambiguity and unsafe input raise rather than degrading to
    # "not found"; main() turns those into the existing error exit.
    governed = governed_path.resolve_governed_path(uid, vault)
    if governed is not None:
        return template_leg._strict_regular_file(
            vault, governed.relative_to(vault), "instance path"
        )

    # A VALIDATOR MUST BE ABLE TO OPEN THE FILES IT EXISTS TO DIAGNOSE.
    #
    # resolve_governed_path() confirms the frontmatter declares the requested
    # uid — correct for a resolver, and wrong as the ONLY path here. check-one's
    # whole job includes reporting STAMPED-YAML and CAPSULE-VERSION defects,
    # which live in files whose frontmatter is malformed or mis-stamped. Routing
    # every lookup through frontmatter verification made those files invisible
    # to the one tool that reports on them: the validator went quiet on exactly
    # the inputs it is for. (My regression, caught by
    # test_typed_mint_phase1::test_companion_is_check_one_source... 2026-08-08.)
    #
    # So the literal bare-uid path stays as a fallback for the governed homes.
    # It is not a weakening of the resolver: resolution still prefers a
    # frontmatter-confirmed match everywhere, and this branch only runs when no
    # file in any home declares the uid — the case where "cannot parse it" and
    # "does not exist" must be told apart by opening it.
    for home in governed_path.GOVERNED_HOMES:
        literal = vault / home / f"{uid}.md"
        if literal.is_file():
            return template_leg._strict_regular_file(
                vault, literal.relative_to(vault), "instance path"
            )

    # Python tools and vault/actions are outside the Markdown-governed
    # filename contract (dev-spec 74f85939 §Governed homes), so they keep the
    # literal shape.
    candidates = [
        vault / "vault" / "tools" / f"{uid}.py",
        vault / "vault" / "tools" / f"{uid}.md",
        vault / "vault" / "tools" / f"{uid}.json",
        vault / "vault" / "actions" / f"{uid}.md",
    ]
    for path in candidates:
        if not path.exists() and not path.is_symlink():
            continue
        return template_leg._strict_regular_file(
            vault,
            path.relative_to(vault),
            "instance path",
        )
    return None


def _parse_flat_frontmatter(text: str) -> dict[str, str]:
    """Best-effort flat key: value scan of an instance's frontmatter block --
    enough for the presence/enum checks below; not a full YAML parse (mirrors
    the lightweight parser pattern used elsewhere, e.g. 40b2f455.py)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([a-zA-Z_][\w]*):\s*(.*)$", line)
        if m:
            val = m.group(2).strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            fm[m.group(1)] = val
    return fm


def run_generic_mint_checks(uid: str, entry_type: str, vault: Path) -> list[str]:
    """Governed Autonomy S2 (bba40cd7) generic verifier tier: placeholder
    survival, section presence, capsule_version presence, enum validity --
    against the SAME §Template leg the minter stamped from (single source,
    vault/tools/lib/template_leg.py). Runs for any type carrying a leg,
    layered alongside whatever bespoke DISPATCHER check-family also exists
    (per-type depth is a later stream; this is the generic tier only).

    Returns [] (not a defect) when the type has no capsule or no §Template leg
    yet -- the generic tier simply doesn't apply there. Returns [] when the
    instance file itself doesn't exist -- not this function's job to report.
    """
    try:
        leg = template_leg.load_verifier_template(vault, entry_type)
    except template_leg.TemplateLegError as exc:
        capsule_path = template_leg.capsule_path_for_type(vault, entry_type)
        if not capsule_path.exists() and not capsule_path.is_symlink():
            return []
        try:
            strict_capsule = template_leg._strict_regular_file(
                vault,
                capsule_path.relative_to(vault),
                f"capsule for verifier type {entry_type!r}",
            )
            capsule_fm = template_leg._frontmatter_mapping(
                strict_capsule.read_text(encoding="utf-8"), strict_capsule
            )
        except (OSError, UnicodeError, template_leg.TemplateLegError) as read_exc:
            return [
                f"[ERROR] {uid} ({entry_type}): TEMPLATE-BINDING — {read_exc}"
            ]
        if capsule_fm.get("mint_mode", "disabled") != "disabled":
            return [
                f"[ERROR] {uid} ({entry_type}): TEMPLATE-BINDING — {exc}"
            ]
        return []

    try:
        instance_path = resolve_instance_path(uid, vault)
    except (ValueError, template_leg.TemplateLegError) as exc:
        return [f"[ERROR] {uid} ({entry_type}): INSTANCE-PATH — {exc}"]
    if instance_path is None:
        return []
    try:
        instance_text = instance_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"[ERROR] {uid} ({entry_type}): BODY-UNREADABLE — {exc}"]

    findings: list[str] = []

    try:
        instance_fm = template_leg._frontmatter_mapping(
            instance_text, instance_path
        )
    except template_leg.TemplateLegError as exc:
        return [
            f"[ERROR] {uid} ({entry_type}): STAMPED-YAML — {exc}"
        ]
    grandfathered = leg.grandfathers(
        instance_fm.get("created"),
        instance_fm.get("capsule_version"),
    )
    if not grandfathered:
        found_sections = template_leg.find_sections(instance_text)
        for title in leg.required_sections():
            if title not in found_sections:
                source = leg.template_path or leg.capsule_path
                findings.append(
                    f"[FAIL] {uid} ({entry_type}): MISSING-SECTION — required "
                    f"section '{title}' not found (template: {source.name})"
                )

    for placeholder_text in template_leg.find_required_placeholders(instance_text, entry_type):
        findings.append(
            f"[FAIL] {uid} ({entry_type}): INCOMPLETE — required placeholder survived: "
            f"\"{placeholder_text}\""
        )

    for stray in template_leg.find_stray_mint_tokens(instance_text, entry_type):
        findings.append(
            f"[ERROR] {uid} ({entry_type}): MALFORMED-MINT — stray {stray} token survived "
            f"(tool defect, not an authoring gap)"
        )

    identity_expected = {
        "uid": uid,
        "type": entry_type,
    }
    identity_actual = {
        field: instance_fm.get(field) for field in identity_expected
    }
    if identity_actual != identity_expected:
        findings.append(
            f"[ERROR] {uid} ({entry_type}): STAMPED-IDENTITY — expected "
            f"{identity_expected!r}, found {identity_actual!r}"
        )
    if "capsule_version" not in instance_fm:
        findings.append(
            f"[WARN] {uid} ({entry_type}): no capsule_version stamp -- not minted by "
            f"`mint file`, or predates Governed Autonomy S2 (legacy instances are not "
            f"migrated; see bba40cd7 scope boundary)"
        )
    elif (
        not grandfathered
        and instance_fm["capsule_version"] != leg.capsule_version
    ):
        findings.append(
            f"[FAIL] {uid} ({entry_type}): CAPSULE-VERSION — stamped "
            f"{instance_fm['capsule_version']!r}, bound capsule is "
            f"{leg.capsule_version!r}"
        )

    for field_name, allowed in leg.enum_hints().items():
        actual = instance_fm.get(field_name)
        if actual is not None and actual not in allowed:
            findings.append(
                f"[FAIL] {uid} ({entry_type}): INVALID-ENUM — {field_name}={actual!r} "
                f"not one of {allowed} (template: {leg.capsule_path.name})"
            )

    return findings


def run_pruning_check(uid: str, vault: Path):
    """Run the shared pruning checker for exactly one resolved UID."""
    return pruning_contract.check_pruning_uid(uid, vault)


def run_vault_audience_check(uid: str, entry_type: str, vault: Path) -> list[str]:
    """B4a contextual vault-audience check for a `type: vault` entry.

    Routes the audience decision through the SAME single adapter every other
    caller uses (lib.audience_gate over the one verified AudiencePolicy) — dev-spec
    0bfa771d requires check-one dispatch group/vault-audience through the shared
    implementations, never a private copy. A no-op unless the entry is a vault
    with a declared audience AND a group authority is installed (cutover active);
    pre-cutover Studios and Studios without the B4a runtime are unaffected.
    """
    if entry_type != "vault":
        return []
    instance_path = resolve_instance_path(uid, vault)
    if instance_path is None:
        return []
    try:
        fm = _parse_flat_frontmatter(instance_path.read_text(encoding="utf-8"))
    except OSError:
        return []
    audience = fm.get("audience")
    if not audience:
        return []
    try:
        from lib.audience_gate import cutover_active, load_policy
    except Exception:
        return []
    try:
        if not cutover_active(vault):
            return []
        policy = load_policy(vault)
    except Exception as exc:
        return [f"[FAIL] {uid} (vault): audience — group authority unavailable: {exc}"]
    outcome = policy.resolve_audience(audience)
    if outcome.ok:
        return []
    return [f"[FAIL] {uid} (vault): audience {audience!r} refused — {outcome.error}"]


def run_checks(
    uid: str,
    entry_type: str,
    vault: Path,
    quiet: bool,
    *,
    pruning_result=None,
) -> tuple[int, str]:
    """Run the per-type check-family (if registered) PLUS the generic mint-tier
    checks (if the type carries a §Template leg) for entry_type, filter to uid,
    return (defects, summary). The two tiers are additive -- per-type depth is a
    later stream (S2 scope boundary); the generic tier covers every leg-bearing
    type today, dispatcher or not."""
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))

    mod_name, fn_name = DISPATCHER.get(entry_type, (None, None))
    dispatcher_findings: list[str] = []

    if mod_name is not None:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name)
        except (ImportError, AttributeError) as e:
            print(f"check-one: failed to load {mod_name}.{fn_name}: {e}", file=sys.stderr)
            sys.exit(2)

        try:
            result = fn(vault)
            # Normalise return: (findings, total, defects) OR (findings, defects) or just findings
            if isinstance(result, tuple) and len(result) >= 2:
                dispatcher_findings = result[0]
            elif isinstance(result, list):
                dispatcher_findings = result
        except Exception as e:
            print(f"check-one: check-family {fn_name} raised {e}", file=sys.stderr)
            sys.exit(2)

    generic_findings = run_generic_mint_checks(uid, entry_type, vault)
    if pruning_result is None:
        pruning_result = run_pruning_check(uid, vault)
    pruning_findings = (
        pruning_result.formatted_findings()
        if pruning_result is not None
        else []
    )
    pruning_applied = bool(
        pruning_result is not None and pruning_result.has_pruning
    )

    if mod_name is None and not generic_findings and not pruning_applied:
        try:
            template_leg.load_verifier_template(vault, entry_type)
            has_leg = True
        except template_leg.TemplateLegError:
            has_leg = False
        if not has_leg:
            return 0, f"check-one {uid} ({entry_type}): no check-family registered — SKIP (exit 0)"

    # Filter dispatcher findings to those mentioning this uid; generic findings are
    # already uid-scoped by construction.
    uid_findings = (
        [f for f in dispatcher_findings if uid in f]
        + generic_findings
        + pruning_findings
        + run_vault_audience_check(uid, entry_type, vault)
    )
    uid_defects = len([f for f in uid_findings if "[FAIL]" in f or "[ERROR]" in f])

    if not quiet:
        for f in uid_findings:
            print(f)

    verdict = "PASS" if uid_defects == 0 else "FAIL"
    summary = f"check-one {uid} ({entry_type}): {len(uid_findings)} finding(s), {uid_defects} defect(s) → {verdict}"
    return uid_defects, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="check-one — targeted single-entry validator (exit 0=PASS, 1=FAIL, 2=error)"
    )
    parser.add_argument("uid", help="8-hex UID of the vault entry to check")
    parser.add_argument("--capsule", help="Force check-family (test-spec / dev-spec / ...)")
    parser.add_argument("--vault-path", help="Path to studio root (default: auto-resolve)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-finding output")
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{8}", args.uid):
        print(f"check-one: uid must be 8-hex; got {args.uid!r}", file=sys.stderr)
        return 2

    vault = Path(args.vault_path) if args.vault_path else VAULT_ROOT

    try:
        return _run(args, vault)
    except (governed_path.AmbiguousGovernedPath,
            governed_path.UnsafeGovernedPath) as exc:
        print(f"check-one: {exc}", file=sys.stderr)
        return 2


def _run(args, vault: Path) -> int:
    pruning_result = run_pruning_check(args.uid, vault)
    entry_type = args.capsule or resolve_type(args.uid, vault)
    if entry_type is None:
        if pruning_result is not None and pruning_result.has_pruning:
            findings = pruning_result.formatted_findings()
            if not args.quiet:
                for finding in findings:
                    print(finding)
            defects = pruning_result.defects
            verdict = "PASS" if defects == 0 else "FAIL"
            print(
                f"check-one {args.uid} (pruning): {len(findings)} finding(s), "
                f"{defects} defect(s) → {verdict}"
            )
            return 0 if defects == 0 else 1
        print(f"check-one: uid {args.uid!r} not found in vault index", file=sys.stderr)
        return 2

    defects, summary = run_checks(
        args.uid,
        entry_type,
        vault,
        args.quiet,
        pruning_result=pruning_result,
    )
    print(summary)
    return 0 if defects == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
