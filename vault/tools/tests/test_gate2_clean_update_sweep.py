#!/usr/bin/env python3
"""Gate 2 — Clean Self-Update — the sweep (test-spec 0c9dbe07, paired with
dev-spec fc4874f4). Runs every behavior that is mechanically checkable without
side effects (no real release build, no real vault mutation, no live network).
Reports PASS/FAIL per behavior; the baseline (pre-build) reads all red — this
build is what should flip the tally green.

Behavior 12 (THE PO WALK) is explicitly out of scope for this script — it is an
agentic_review verification method that requires a cold concierge boot in a
seeded stranger studio, which is Po's job (Mike activates her), not a mechanical
check. It reports SKIPPED here, not PASS or FAIL.

Behaviors 13-16 (LOCK-AMENDMENT 3, finding 5d4bbbf2, added by Talos T24
2026-07-02): RECEIPT-LAST, DUAL-HASH RECEIPT, CONFIRM HARD-STOP, and the
end-to-end apply-with-housekeeping fixture. These re-verify structurally what
THE FLOOR TEST (behavior 10) already proves at the code level — kept as
separate named behaviors here so the sweep's own tally names each covenant
property the walk found broken, rather than folding them silently into "the
floor test passed."

Exit 0 = all non-skipped behaviors PASS, Exit 1 = at least one FAIL.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = ROOT / "vault" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
PLAYBOOK = ROOT / "vault" / "playbooks" / "71f186cf.md"
CONCIERGE = ROOT / ".tropo" / "concierge" / "activate.md"
NAMESPACE_MOD = ROOT / "vault" / "tools" / "lib" / "tropo_update_namespace.py"
RECEIPT_MOD = ROOT / "vault" / "tools" / "lib" / "tropo_update_receipt.py"
CONFIRM_MOD = ROOT / "vault" / "tools" / "lib" / "tropo_update_confirm_gate.py"
FLOOR_TEST = ROOT / "vault" / "tools" / "tests" / "test_clean_update_floor.py"
MANIFEST_GEN = ROOT / "vault" / "tools" / "tropo-generate-update-manifest.py"
UPDATES_DIR = ROOT / "vault" / "updates"
MIGRATIONS_DIR = ROOT / ".tropo" / "playbooks" / "migrations"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

results = []  # (n, description, "PASS"|"FAIL"|"SKIPPED", detail)


def check(n, desc, ok, detail=""):
    results.append((n, desc, "PASS" if ok else "FAIL", detail))


def skip(n, desc, detail):
    results.append((n, desc, "SKIPPED", detail))


def b1_namespace_predicate():
    spec = importlib.util.spec_from_file_location("tropo_update_namespace", NAMESPACE_MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = {
        "vault/tropo-foo.md": True,
        "vault/files/my-project-1a2b3c4d.md": False,
        "vault/files/1a2b3c4d.md": False,
        ".tropo/boot-config.md": True,
    }
    ok = all(mod.is_os_component(p) == expect for p, expect in cases.items())

    # LOCK-AMENDMENT 2 — category (d): manifest-listed machinery classifies REPLACE when
    # clean, USER_MODIFIED_SHIPPED when drifted; unlisted/spoofed paths stay PRESERVE.
    manifest_index = {"vault/playbooks/71f186cf.md": "a" * 64}
    d_clean = mod.classify("vault/playbooks/71f186cf.md", manifest_index=manifest_index, current_hash="a" * 64) == mod.REPLACE
    d_drifted = mod.classify("vault/playbooks/71f186cf.md", manifest_index=manifest_index, current_hash="b" * 64) == mod.USER_MODIFIED_SHIPPED
    d_spoofed = mod.classify("vault/files/my-tropo-notes-5a5a5a5a.md", manifest_index=manifest_index) == mod.PRESERVE

    # LOCK-AMENDMENT 2 re-verify F1/F2 — parse a REAL shipped MANIFEST.md (not a fixture)
    # and confirm the truncated-hash prefix-match works. Non-fatal if the real release
    # artifact isn't present on this machine (e.g. a CI runner without tropo-releases/).
    real_manifest_path = Path("/Users/mike/dev/tropo-releases/v1.77.0/builds/tropo-os-v1.77.0/MANIFEST.md")
    if real_manifest_path.exists():
        real_index, real_skipped = mod.parse_manifest_md(real_manifest_path.read_text())
        real_format_ok = len(real_index) == 957 and real_skipped <= 1
        sample_path, sample_hash = next(iter(real_index.items()))
        prefix_match_ok = mod.classify(sample_path, manifest_index=real_index,
                                        current_hash=sample_hash + "f" * (64 - len(sample_hash))) == mod.REPLACE
    else:
        real_format_ok = True  # can't verify, don't fail the sweep for a missing local artifact
        prefix_match_ok = True

    ok = ok and d_clean and d_drifted and d_spoofed and real_format_ok and prefix_match_ok
    check(1, "Namespace predicate deterministic + content-blind (incl. category (d), real-manifest parse)", ok,
          f"{cases} d_clean={d_clean} d_drifted={d_drifted} d_spoofed={d_spoofed} "
          f"real_format_ok={real_format_ok} prefix_match_ok={prefix_match_ok}")


def _live_stale_path_hits(text, old_path):
    """Lines mentioning `old_path` that are NOT explanatory ('re-homed from X to Y',
    changelog/reactivation_note prose) — i.e. genuine surviving live references.
    A line that mentions the current path too is describing the migration, not
    using the old path as a real target; that's the historical-mention exception
    (same posture as Self-Healing's changelog exception)."""
    new_path = "vault/updates/"
    explanatory_markers = ("re-homed", "reactivat", "dev-spec fc4874f4", "Gate 2", "Gate-2")
    hits = []
    for ln in text.splitlines():
        if old_path not in ln:
            continue
        if new_path in ln or any(m in ln for m in explanatory_markers):
            continue  # narrating the migration ("re-homed from X to Y"), not a live reference
        hits.append(ln.strip())
    return hits


def b2_playbook_reconciliation():
    text = PLAYBOOK.read_text()
    # Check the BODY only (frontmatter changelog legitimately narrates the old path
    # it swept — that's historical record, not live logic; same exception class as
    # the concierge's changelog rows).
    body = text.split('\n---\n', 2)[-1] if text.count('\n---\n') >= 2 else text
    no_system_updates = len(_live_stale_path_hits(body, "system/updates/")) == 0
    has_predicate_rule = "ca6e5824" in text and "Namespace Predicate" in text
    top_level_version = re.search(r"^version:\s*'([\d.]+)'", text, re.MULTILINE)
    # LOCK-AMENDMENT 3 bumped the playbook to v2.3 (Talos T24). Pin to the current
    # expected version rather than an ever-staler hardcoded string — bump this
    # constant deliberately whenever the playbook version bumps again.
    EXPECTED_VERSION = '2.3'
    is_current_version = top_level_version is not None and top_level_version.group(1) == EXPECTED_VERSION
    has_category_d = "category (d)" in text and "USER_MODIFIED_SHIPPED" in text and "4496553c" in text
    ok = no_system_updates and has_predicate_rule and is_current_version and has_category_d
    check(2, f"Playbook reconciliation complete (zero live system/updates/, predicate Rule present, v{EXPECTED_VERSION} incl. category (d)+F1-F3)",
          ok, f"no_system_updates={no_system_updates} has_predicate_rule={has_predicate_rule} "
              f"top_level_version={top_level_version.group(1) if top_level_version else None} has_category_d={has_category_d}")


def b3_update_discovery_contract():
    spec = importlib.util.spec_from_file_location("gen", MANIFEST_GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    manifest = mod.build_manifest(mod.load_release_catalog(mod.INDEX_PATH))
    up_to_date = mod.render_for_client(manifest, manifest["current"])
    available = mod.render_for_client(manifest, manifest["updates"][0]["version"]) if manifest["updates"] else None
    migration_required = mod.render_for_client(manifest, "0.0.1")
    malformed = mod.render_for_client(manifest, "not-a-version")
    ok = (
        up_to_date.get("updates") == []
        and migration_required.get("migration_required") is True
        and "message" in migration_required
        and "updates" in malformed and malformed.get("updates") == []  # graceful, not a crash
    )
    check(3, "Update discovery contract (3 shapes + graceful-on-garbage + offline-shaped)", ok,
          f"up_to_date={up_to_date} migration_required={migration_required} malformed={malformed}")


def b4_incompatibility_halt_documented():
    text = PLAYBOOK.read_text()
    has_step05 = "Step 0.5" in text and "incompatibility halt" in text.lower()
    delivers_verbatim = "verbatim" in text.lower() and "migration_required" in text
    check(4, "Apply-time incompatibility halt documented as Step 0.5, verbatim delivery", has_step05 and delivers_verbatim)


def b5_state_machine_rehomed():
    dirs_exist = all((UPDATES_DIR / d).is_dir() for d in ("pending", "applied", "failed", "receipts"))
    history_exists = (UPDATES_DIR / "update-history.jsonl").exists()
    no_system_dir = not (ROOT / "system").exists()
    check(5, "State machine re-homed to vault/updates/ (pending/applied/failed/receipts + history; system/ gone)",
          dirs_exist and history_exists and no_system_dir,
          f"dirs_exist={dirs_exist} history_exists={history_exists} no_system_dir={no_system_dir}")


def b6_v11_mechanisms_verbatim():
    text = PLAYBOOK.read_text()
    markers = ["dry-run-diff", "commit-divergence-halt", "log-and-skip", "Idempotent",
               "version gap", "No auto-rollback" if "No auto-rollback" in text else "no auto-rollback"]
    hits = {m: (m.lower() in text.lower()) for m in markers}
    ok = all(hits.values())
    check(6, "v1.1 mechanisms carried forward verbatim (dry-run/divergence/skip/idempotent/version-gap/no-rollback)",
          ok, str(hits))


def b7_covenant_receipt():
    text = PLAYBOOK.read_text()
    has_receipt_section = "The Covenant Receipt" in text
    has_step45 = "Step 4.5" in text
    # LOCK-AMENDMENT 3: the receipt gained a real code module (tropo_update_receipt.py) —
    # RECEIPT-LAST + dual-hash are structural now, not playbook-authored prose alone.
    receipt_lib_exists = RECEIPT_MOD.exists()
    ok = has_receipt_section and has_step45 and receipt_lib_exists
    check(7, "Per-apply covenant receipt documented (Step 4.5, dual-hash manifest, receipt module exists)", ok,
          f"has_receipt_section={has_receipt_section} has_step45={has_step45} receipt_lib_exists={receipt_lib_exists}")


def b8_concierge_route_reconciled():
    text = CONCIERGE.read_text()
    # Exclude historical changelog rows AND explanatory "re-homed from X to Y" prose
    # (same exception class as Self-Healing's changelog exception) — only count hits
    # that mention the old path WITHOUT also narrating the new one.
    live_hits = [ln for ln in _live_stale_path_hits(text, "system/updates/")
                 if not ln.strip().startswith("- **v1.4")]
    has_verbatim_note = "VERBATIM" in text and "migration_required" in text
    check(8, "Concierge route reconciled (zero live system/updates/ hits, migration_required delivered VERBATIM)",
          len(live_hits) == 0 and has_verbatim_note, f"live_hits={live_hits}")


def b9_migrations_and_steward_revalidated():
    ok = True
    detail = {}
    for fname in ("migrate-file-status.playbook.md", "migrate-index-format.playbook.md"):
        text = (MIGRATIONS_DIR / fname).read_text()
        no_system_updates = len(_live_stale_path_hits(text, "system/updates/")) == 0
        detail[fname] = no_system_updates
        ok = ok and no_system_updates
    steward_text = (ROOT / ".tropo" / "system" / "vault-steward.template.md").read_text()
    steward_hits = _live_stale_path_hits(steward_text, "system/updates/")
    steward_ok = len(steward_hits) == 0
    detail["vault-steward.template.md"] = steward_ok
    ok = ok and steward_ok
    check(9, "Reference migrations + vault-steward re-validated (zero live system/updates/ refs)", ok, str(detail))


def b10_floor_test():
    normal = subprocess.run(["python3", str(FLOOR_TEST)], capture_output=True, text=True, timeout=60)
    gauntlet = subprocess.run(["python3", str(FLOOR_TEST), "--gauntlet"], capture_output=True, text=True, timeout=60)
    ok = normal.returncode == 0 and gauntlet.returncode == 0
    check(10, "THE FLOOR TEST (real run PASS + gauntlet PASS = violation correctly caught)", ok,
          f"normal_exit={normal.returncode} gauntlet_exit={gauntlet.returncode}")


def b11_covenant_gauntlet_wired():
    # Structural check only — does NOT invoke tropo-build-release.py (real build has side
    # effects: version bump, release-dir creation, Pipeline Activation Key requirement).
    # Confirms Step 10.7 exists and is wired to call the floor test in both modes and
    # sys.exit on failure, matching the mechanism b10 already proved works standalone.
    text = (ROOT / "vault" / "tools" / "tropo-build-release.py").read_text()
    has_step107 = "Step 10.7" in text and "Covenant Gate" in text
    calls_gauntlet = "'--gauntlet'" in text
    hard_exits = "sys.exit(7)" in text
    ok = has_step107 and calls_gauntlet and hard_exits
    check(11, "Covenant gauntlet wired as a blocking build gate (Step 10.7, structural — not a real build run)",
          ok, f"has_step107={has_step107} calls_gauntlet={calls_gauntlet} hard_exits={hard_exits}")


def b12_po_walk():
    skip(12, "THE PO WALK (agentic_review — cold concierge boot in a seeded stranger studio)",
         "Out of scope for a mechanical sweep script. Po's job; Mike activates her per the "
         "standing division of labor (Talos builds, Argus verifies, Po walks, Mike signs).")


def b13_receipt_last_structural():
    """LOCK-AMENDMENT 3, F6. Playbook names Step 4.4 (housekeeping) BEFORE Step 4.5/4.6
    (receipt compute + seal); the guard (ReceiptSeal) exists as code and actually raises
    when a write is attempted after seal() — not just documented as a step order."""
    text = PLAYBOOK.read_text()
    has_step44_before_45 = (
        "Step 4.4" in text and "Step 4.5" in text and "Step 4.6" in text
        and text.index("Step 4.4") < text.index("Step 4.5") < text.index("Step 4.6")
    )
    names_receipt_last = "RECEIPT-LAST" in text
    mod = _load("tropo_update_receipt", RECEIPT_MOD)
    seal = mod.ReceiptSeal()
    seal.record_write("a")
    seal.seal("r.md")
    guard_raises = False
    try:
        seal.record_write("b")
    except mod.PostReceiptWriteError:
        guard_raises = True
    ok = has_step44_before_45 and names_receipt_last and guard_raises
    check(13, "RECEIPT-LAST structural (Step 4.4 before 4.5/4.6 in playbook; ReceiptSeal raises post-seal)",
          ok, f"has_step44_before_45={has_step44_before_45} names_receipt_last={names_receipt_last} guard_raises={guard_raises}")


def b14_dual_hash_receipt():
    """LOCK-AMENDMENT 3, F6. content_hash() canonicalizes nav-block spans out (proven
    against the real synthetic nav-block shape); playbook documents both the content-hash
    proof and the honest nav_chrome_disclosure list."""
    mod = _load("tropo_update_receipt", RECEIPT_MOD)
    pre = "# Title\n\nBody text.\n"
    post = f"# Title\n\n{mod.NAV_BLOCK_START}\n**\U0001f517 This file** — UID `deadbeef` · type `note`\n{mod.NAV_BLOCK_END}\n\nBody text.\n"
    canonicalizes = mod.content_hash(pre) == mod.content_hash(post)
    byte_differs = mod.byte_hash(pre) != mod.byte_hash(post)
    text = PLAYBOOK.read_text()
    names_dual_hash = "nav_chrome_disclosure" in text and "content_hash_mismatches" in text
    ok = canonicalizes and byte_differs and names_dual_hash
    check(14, "Dual-hash receipt (content_hash canonicalizes nav-block spans; byte_hash does not; playbook documents both)",
          ok, f"canonicalizes={canonicalizes} byte_differs={byte_differs} names_dual_hash={names_dual_hash}")


def b15_confirm_hard_stop():
    """LOCK-AMENDMENT 3, F1-confirm. ConfirmGate.require_cleared() raises for an
    unacked item, a blanket ack recorded under a different key does NOT clear it, and
    the class exposes no bulk-approve method (structural, not just behavioral)."""
    mod = _load("tropo_update_confirm_gate", CONFIRM_MOD)
    gate = mod.ConfirmGate()
    gate.register("vault/files/target.md", kind="user_modified_shipped", message="test")
    unacked_raises = False
    try:
        gate.require_cleared("vault/files/target.md")
    except mod.ConfirmNotRecordedError:
        unacked_raises = True
    gate.register("__blanket__", kind="blanket", message="user said go ahead")
    gate.record_ack("__blanket__", "approved")
    blanket_does_not_clear = False
    try:
        gate.require_cleared("vault/files/target.md")
    except mod.ConfirmNotRecordedError:
        blanket_does_not_clear = True
    gate.record_ack("vault/files/target.md", "approved")
    per_item_clears = True
    try:
        gate.require_cleared("vault/files/target.md")
    except mod.ConfirmNotRecordedError:
        per_item_clears = False
    no_bulk_api = not any(
        name for name in dir(mod.ConfirmGate)
        if not name.startswith("_") and ("all" in name.lower() or "bulk" in name.lower()) and "record" not in name.lower()
        and name not in ("all_registered",)  # a read-only lister, not an approve-everything method
    )
    ok = unacked_raises and blanket_does_not_clear and per_item_clears and no_bulk_api
    check(15, "Confirm hard-stop structural (unacked raises; blanket ack under another key never clears; per-item ack does; no bulk-approve API)",
          ok, f"unacked_raises={unacked_raises} blanket_does_not_clear={blanket_does_not_clear} "
              f"per_item_clears={per_item_clears} no_bulk_api={no_bulk_api}")


def b16_e2e_housekeeping_fixture():
    """LOCK-AMENDMENT 3, item 4. THE FLOOR TEST's e2e apply-with-housekeeping
    simulation is present and its own normal run (which includes this fixture)
    passes — proven at the code level by re-running the floor test itself, since
    the e2e check is now part of its main() gate (not a separate script to drift
    out of sync with)."""
    text = FLOOR_TEST.read_text()
    has_e2e_fixture = "check_e2e_apply_with_housekeeping_and_receipt" in text
    has_real_walk_crosscheck = "check_against_real_walk_artifacts" in text
    r = subprocess.run(["python3", str(FLOOR_TEST)], capture_output=True, text=True, timeout=60)
    floor_test_passes = r.returncode == 0
    ok = has_e2e_fixture and has_real_walk_crosscheck and floor_test_passes
    check(16, "E2E floor-test fixture includes post-apply housekeeping + real-walk cross-check (LOCK-AMENDMENT 3 item 4)",
          ok, f"has_e2e_fixture={has_e2e_fixture} has_real_walk_crosscheck={has_real_walk_crosscheck} "
              f"floor_test_passes={floor_test_passes} floor_test_stdout_tail={(r.stdout or '')[-200:]!r}")


def main() -> int:
    b1_namespace_predicate()
    b2_playbook_reconciliation()
    b3_update_discovery_contract()
    b4_incompatibility_halt_documented()
    b5_state_machine_rehomed()
    b6_v11_mechanisms_verbatim()
    b7_covenant_receipt()
    b8_concierge_route_reconciled()
    b9_migrations_and_steward_revalidated()
    b10_floor_test()
    b11_covenant_gauntlet_wired()
    b12_po_walk()
    b13_receipt_last_structural()
    b14_dual_hash_receipt()
    b15_confirm_hard_stop()
    b16_e2e_housekeeping_fixture()

    print("=== Gate 2 — clean self-update sweep (test-spec 0c9dbe07 + LOCK-AMENDMENT 3) ===\n")
    fails = 0
    for n, desc, verdict, detail in results:
        marker = {"PASS": "✓", "FAIL": "✗", "SKIPPED": "○"}[verdict]
        print(f"{marker} [{n:>2}] {verdict:8s} — {desc}")
        if detail:
            print(f"         {detail}")
        if verdict == "FAIL":
            fails += 1

    passed = sum(1 for r in results if r[2] == "PASS")
    skipped = sum(1 for r in results if r[2] == "SKIPPED")
    print(f"\n{passed} passed, {fails} failed, {skipped} skipped (out of {len(results)} behaviors)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
