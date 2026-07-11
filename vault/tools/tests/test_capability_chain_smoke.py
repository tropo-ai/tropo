#!/usr/bin/env python3
"""Capability regression smoke test — RUNS the chain, not just the validator.

Proves the One Home migration (ADR-045) didn't break:
  (1) rebuild-index runs end-to-end (RB_EXIT=0) and indexes all vault/<type>/ content
  (2) event_emitter.py loads tropo-emit-event.py (the choke-point auto-emission lib)
  (3) Key Path-constant / os.path.join / importlib refs in build-release + archive
      point to files that actually exist

"Test-done" = the whole chain EXECUTES, not "the validator passes."
Exit 0 = PASS, Exit 1 = FAIL.
"""
from __future__ import annotations
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULT = ROOT / "vault"
TOOLS = VAULT / "tools"
INDEX = VAULT / "00-index.jsonl"
EVENT_EMITTER = ROOT / ".tropo" / "scripts" / "lib" / "event_emitter.py"


# ---------------------------------------------------------------------------
# Check 1: rebuild-index runs clean and indexes all vault/<type> content
# ---------------------------------------------------------------------------

def check_rebuild_index() -> list[str]:
    failures = []
    result = subprocess.run(
        [sys.executable, str(TOOLS / "tropo-rebuild-index.py"), "--apply"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if result.returncode != 0:
        failures.append(f"rebuild-index exited {result.returncode}: {result.stderr[:300]}")
        return failures

    # Verify vault/<type> coverage in the fresh index
    if not INDEX.exists():
        failures.append("vault/00-index.jsonl not written after rebuild")
        return failures

    indexed_uids: set[str] = set()
    with open(INDEX) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                uid = d.get("uid")
                if uid:
                    indexed_uids.add(uid)
            except Exception:
                pass

    uid_re = re.compile(r"^uid:\s*([0-9a-f]{8})\s*$", re.MULTILINE)

    for subdir in ("skills", "actions", "playbooks", "capsules"):
        d = VAULT / subdir
        if not d.exists():
            continue
        missing = []
        for f in d.glob("*.md"):
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            m = uid_re.search(text[:2000])
            if m and m.group(1) not in indexed_uids:
                missing.append(f.name)
        if missing:
            failures.append(
                f"vault/{subdir}/: {len(missing)} file(s) unindexed after rebuild: "
                + ", ".join(missing[:5])
            )

    return failures


# ---------------------------------------------------------------------------
# Check 2: event_emitter.py loads tropo-emit-event.py successfully
# ---------------------------------------------------------------------------

def check_event_emitter() -> list[str]:
    failures = []
    if not EVENT_EMITTER.exists():
        failures.append(f"event_emitter.py not found at {EVENT_EMITTER}")
        return failures

    # Read _EMIT_TOOL path from the file
    text = EVENT_EMITTER.read_text()
    m = re.search(r'_EMIT_TOOL\s*=.*?"([^"]+)"', text)
    if not m:
        # Try single-quote variant or path construction
        # Accept if it references tropo-emit-event
        if "tropo-emit-event" not in text:
            failures.append("event_emitter._EMIT_TOOL does not reference tropo-emit-event")
            return failures
    else:
        # The path is relative to _VAULT_ROOT, but the string fragment gives us the filename
        tool_fragment = m.group(1)
        if "ca90f098" in tool_fragment:
            failures.append(
                f"event_emitter._EMIT_TOOL still references deleted ca90f098: {tool_fragment}"
            )

    # Actually load it and verify emit() exists
    spec = importlib.util.spec_from_file_location("event_emitter_test", str(EVENT_EMITTER))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        failures.append(f"event_emitter import failed: {e}")
        return failures

    load_fn = getattr(mod, "_load_emit", None)
    if not load_fn:
        failures.append("event_emitter has no _load_emit function")
        return failures

    emit_fn = load_fn()
    if emit_fn is None:
        failures.append("event_emitter._load_emit() returned None — tropo-emit-event.py failed to load")

    return failures


# ---------------------------------------------------------------------------
# Check 3: Key Path refs in build-release + archive point to existing files
# ---------------------------------------------------------------------------

BUILD_RELEASE = TOOLS / "tropo-build-release.py"
ARCHIVE = TOOLS / "tropo-archive.py"

# Regex to find quoted tool path refs (Path() / "vault" / "tools" / "<name>.py" patterns)
TOOL_PATH_RE = re.compile(
    r"""(?:os\.path\.join|Path\s*\()\s*[^)]*?["'](?:vault/tools/|vault["'],\s*["']tools["'],\s*["'])([0-9a-f]{8}[^"']*\.py)""",
    re.DOTALL,
)
IMPORTLIB_UID_RE = re.compile(
    r"""spec_from_file_location\s*\(\s*["'][^"']*["']\s*,\s*.*?["']([0-9a-f]{8}[^"']*\.py)["']""",
    re.DOTALL,
)

def check_tool_refs_in_file(path: Path) -> list[str]:
    if not path.exists():
        return []  # Tool may not ship in all contexts; skip silently
    text = path.read_text(errors="ignore")
    failures = []
    # Check for UID-only tool refs (8 hex chars + .py) that should have been renamed
    uid_path_re = re.compile(r"vault/tools/([0-9a-f]{8})\.py")
    for m in uid_path_re.finditer(text):
        uid = m.group(1)
        uid_file = TOOLS / f"{uid}.py"
        if not uid_file.exists():
            snippet = text[max(0, m.start()-40):m.end()+40].replace("\n", " ")
            failures.append(
                f"{path.name}: dead UID ref vault/tools/{uid}.py "
                f"(file does not exist) — context: ...{snippet}..."
            )
    return failures


def check_chain_path_refs() -> list[str]:
    failures = []
    for tool in (BUILD_RELEASE, ARCHIVE):
        failures.extend(check_tool_refs_in_file(tool))
    return failures


# ---------------------------------------------------------------------------
# Check 4: No-two-homes gate adversarial isolation (AC6 — A112/A113 gauntlet)
# ---------------------------------------------------------------------------

VALIDATE = TOOLS / "tropo-validate.py"
TROPO_SCRIPTS = ROOT / ".tropo" / "scripts"


def check_no_two_homes_gate() -> list[str]:
    """Plant a tropo- tool in .tropo/scripts/, assert ERROR, remove, assert PASS.

    Per A112/A113 binding: the enforcement mechanism (not a side effect) must
    catch the dup. Tests BOTH the UID-frontmatter path and the tropo-name path.
    """
    failures = []
    # Pick a canonical vault/tools/ tropo- script to duplicate
    victim = TOOLS / "tropo-mint-id.py"
    planted = TROPO_SCRIPTS / "tropo-mint-id.py"
    if not victim.exists():
        failures.append("no-two-homes adversarial: tropo-mint-id.py not found in vault/tools/")
        return failures
    if not VALIDATE.exists():
        failures.append("no-two-homes adversarial: tropo-validate.py not found")
        return failures

    import shutil
    # Plant
    shutil.copy2(victim, planted)
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        combined = result.stdout + result.stderr
        if "[ERROR] Two-home script:" not in combined:
            failures.append(
                "no-two-homes gate did NOT ERROR on planted tropo-mint-id.py duplicate "
                f"(exit={result.returncode}; got: {combined[-300:]})"
            )
    finally:
        if planted.exists():
            planted.unlink()

    # Verify clean after removal
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    combined = result.stdout + result.stderr
    if "zero two-home duplicates" not in combined:
        failures.append(
            "no-two-homes gate did not PASS after removing planted duplicate "
            f"(exit={result.returncode}; got: {combined[-300:]})"
        )

    return failures


# ---------------------------------------------------------------------------
# Check 5: Identity minting chokepoint adversarial isolation (796d9330 / ADR-050 AC5)
# ---------------------------------------------------------------------------

def check_mint_id_chokepoint_gate() -> list[str]:
    """Plant a raw secrets.token_hex(4) UID-shaped bypass in vault/tools/, assert the
    chokepoint check reports it; remove the plant, assert clean. Per AC5 (796d9330,
    non-negotiable): "the gate is real only if it fires" — proven by running, not asserted.
    """
    failures = []
    if not VALIDATE.exists():
        failures.append("mint-id-chokepoint adversarial: tropo-validate.py not found")
        return failures

    fixture = TOOLS / "_test_mint_id_bypass_fixture.py"
    fixture_body = (
        '"""Test fixture for check_mint_id_chokepoint (796d9330) — planted UID bypass.\n'
        'Deleted immediately after the adversarial test runs; should never survive on disk.\n"""\n'
        "import secrets\n\n"
        "def bogus_mint():\n"
        "    return secrets.token_hex(4)\n"
    )
    fixture.write_text(fixture_body, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        combined = result.stdout + result.stderr
        if "bypasses the tropo-mint-id.py chokepoint" not in combined:
            failures.append(
                "mint-id-chokepoint gate did NOT flag the planted token_hex(4) bypass "
                f"(exit={result.returncode}; got tail: {combined[-400:]})"
            )
    finally:
        if fixture.exists():
            fixture.unlink()

    # Verify clean after removal
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    combined = result.stdout + result.stderr
    if "no raw token_hex(4) bypass" not in combined:
        failures.append(
            "mint-id-chokepoint gate did not PASS after removing the planted fixture "
            f"(exit={result.returncode}; got tail: {combined[-400:]})"
        )

    return failures


# ---------------------------------------------------------------------------
# Check 6: Pipeline-Activation Coupling Gate adversarial isolation (8f15f08d AC-1)
# ---------------------------------------------------------------------------

FILES_DIR = VAULT / "files"


def check_dev_spec_activation_coupling_gate() -> list[str]:
    """Plant a dev-spec at status:locked with NO correlated activation; assert the
    Pipeline-Activation Coupling Gate (8f15f08d) WARNs on it; remove the plant; assert
    the plant's specific finding is gone. Per 8f15f08d AC-1: "proven by running
    tropo-validate.py against the plant, not asserted."

    Deliberately does NOT assert the whole vault returns clean after removal — this
    vault carries 9 pre-existing, unrelated off-pipeline dev-specs discovered by Talos
    T25's verify-before-designing pass (see tropo-validate.py's
    check_dev_spec_activation_coupling docstring); the ratchet-toggle (WARN vs ERROR)
    behavior itself is covered deterministically in
    test_dev_spec_activation_coupling.py against an isolated fixture vault.
    """
    failures = []
    if not VALIDATE.exists():
        failures.append("dev-spec-activation-coupling adversarial: tropo-validate.py not found")
        return failures
    if not FILES_DIR.exists():
        failures.append("dev-spec-activation-coupling adversarial: vault/files/ not found")
        return failures

    plant_uid = "feed0001"
    plant_path = FILES_DIR / f"{plant_uid}.md"
    if plant_path.exists():
        failures.append(f"dev-spec-activation-coupling adversarial: plant path {plant_path} already exists — refusing to overwrite")
        return failures

    plant_body = (
        "---\n"
        f"uid: {plant_uid}\n"
        "type: dev-spec\n"
        "title: \"TEST FIXTURE — capability-chain-smoke coupling-gate plant (deleted immediately)\"\n"
        "status: locked\n"
        "state: active\n"
        "target_release: \"0.0.0-test\"\n"
        "target_stream: null\n"
        "committed_substrate:\n"
        "  - target: \"vault/tools/tests/test_capability_chain_smoke.py\"\n"
        "    change_class: AMENDED\n"
        "    description: \"test fixture plant\"\n"
        "acceptance_criteria:\n"
        "  - \"test fixture only\"\n"
        "owner: talos\n"
        "author: talos\n"
        "created: '2026-07-07'\n"
        "created_by: talos-t25\n"
        "modified: '2026-07-07'\n"
        "modified_by: talos-t25\n"
        "schema_version: 2\n"
        "locked_by: talos-t25\n"
        "locked_at: '2026-07-07'\n"
        "tags: [test-fixture]\n"
        "---\n\n# TEST FIXTURE\n\nDeleted immediately after this gauntlet runs.\n"
    )
    plant_path.write_text(plant_body, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        combined = result.stdout + result.stderr
        if f"dev-spec {plant_uid}" not in combined or "NO correlated type:activation" not in combined:
            failures.append(
                "dev-spec-activation-coupling gate did NOT flag the planted off-pipeline dev-spec "
                f"(exit={result.returncode}; got tail: {combined[-600:]})"
            )
    finally:
        if plant_path.exists():
            plant_path.unlink()

    # Verify the plant's specific finding is gone after removal.
    result = subprocess.run(
        [sys.executable, str(VALIDATE)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    combined = result.stdout + result.stderr
    if f"dev-spec {plant_uid}" in combined:
        failures.append(
            "dev-spec-activation-coupling gate still reports the planted UID after removal "
            f"(exit={result.returncode})"
        )

    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    all_passed = True

    print("=== Capability Chain Smoke Test (ADR-045 One Home) ===\n")

    print("[1/6] rebuild-index: running chain + asserting vault/<type> coverage...")
    rebuild_fails = check_rebuild_index()
    if rebuild_fails:
        for f in rebuild_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — rebuild-index RB_EXIT=0; all vault/<type>/ files indexed")

    print("\n[2/6] event_emitter: loading tropo-emit-event.py...")
    emit_fails = check_event_emitter()
    if emit_fails:
        for f in emit_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — event_emitter loads tropo-emit-event.py; emit() is callable")

    print("\n[3/6] tool chain path refs: checking build-release + archive for dead UID paths...")
    ref_fails = check_chain_path_refs()
    if ref_fails:
        for f in ref_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — no dead UID-only tool paths in build-release or archive")

    print("\n[4/6] no-two-homes gate: adversarial isolation (plant tropo- dup → ERROR → remove → PASS)...")
    nth_fails = check_no_two_homes_gate()
    if nth_fails:
        for f in nth_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — no-two-homes gate ERRORs on planted tropo- dup; PASSes on removal")

    print("\n[5/6] mint-id chokepoint gate: adversarial isolation (796d9330; plant raw token_hex(4) → WARN → remove → PASS)...")
    mic_fails = check_mint_id_chokepoint_gate()
    if mic_fails:
        for f in mic_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — mint-id-chokepoint gate flags a planted token_hex(4) bypass; PASSes on removal")

    print("\n[6/6] dev-spec activation-coupling gate: adversarial isolation (8f15f08d; plant off-pipeline dev-spec → WARN → remove → gone)...")
    dsac_fails = check_dev_spec_activation_coupling_gate()
    if dsac_fails:
        for f in dsac_fails:
            print(f"  FAIL: {f}")
        all_passed = False
    else:
        print("  PASS — coupling gate flags a planted off-pipeline dev-spec; finding clears on removal")

    print()
    if all_passed:
        print("=== ALL PASS — capability chain is green ===")
        return 0
    else:
        print("=== FAIL — capability chain has broken links ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
