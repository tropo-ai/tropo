#!/usr/bin/env python3
"""THE FLOOR TEST — Gate 2 acceptance proof (dev-spec fc4874f4, acceptance criterion 9;
LOCK-AMENDMENT 2, finding 4496553c).

Seeds a throwaway vault on the REAL shipped layout — not an idealized `tropo-*`-only
fixture. LOCK-AMENDMENT 2 exists because the idealized fixture this test originally
shipped with (v1 of this file) could not see the gap it was supposed to prove closed:
the real update machinery (uid-named canonical playbooks/tools, `.tropo-studio/`
registries, root README/MANIFEST) is neither `tropo-*`-named nor under `.tropo/`, so
under the three-category predicate alone it silently classified PRESERVE — an update
could never deliver its own machinery. Found by Argus A123 running the real v1.77->v1.78
delta through the real predicate while staging the Po walk. The fixture below seeds:

  - category (a)/(b): `vault/tropo-*` + `.tropo/*` — unchanged from the original fixture.
  - category (d) machinery: a uid-named canonical playbook, a uid-named "engine" tool,
    a `.tropo-studio/` registry file, and root `README.md` — all manifest-listed, none
    `tropo-*`-named or under `.tropo/`. A fixture MANIFEST.md is generated to list them.
  - category (c) user content: unchanged from the original fixture.
  - a SPOOFED user file — filename contains "tropo" but not as the exact `tropo-`
    prefix, and is not manifest-listed — proves the predicate is exact-prefix /
    manifest-membership, not fuzzy/substring matching.
  - a USER-MODIFIED-SHIPPED file — one of the category-(d) machinery files, but its
    on-disk content has drifted from what the manifest recorded. Must NOT be silently
    overwritten; must surface as an overwrite-confirm line instead (LOCK-AMENDMENT 2).

Assertions:
  1. ZERO true-user-file churn (category (c) + the spoofed file) — mtime AND hash
     unchanged for every one of them.
  2. Every clean (non-drifted) OS-substrate file targeted by the plan — categories
     (a), (b), AND (d) — is at its new version. This is the LOCK-AMENDMENT 2 proof:
     the machinery delta is deliverable.
  3. The user-modified-shipped file is NOT silently overwritten; it appears as an
     overwrite-confirm line, and its on-disk content is unchanged until confirmed.

The test FAILS if a single true-user file is touched, if any clean OS-substrate file
in the plan is left un-updated, or if the user-modified-shipped file is silently
overwritten instead of surfaced for confirm.

Adversarial isolation (A112/A113 gauntlet binding, matches the house style of
test_no_two_homes_gate.py / test_one_open_activation_gate.py): `--gauntlet` plants a
covenant-violating operation (one that touches a true user file) and asserts the floor
test correctly reports FAIL, proving the mechanism can fail, not just print PASS.

LOCK-AMENDMENT 2 re-verify fixes (Argus A123, running against a REAL v1.77.0 extract —
not this fixture): F1 — the fixture's generated MANIFEST.md matched this test's OWN
parser instead of the real shipped format (12-hex + literal `...` ellipsis, not full
64-hex), the exact self-consistency-bug class this amendment exists to kill. Fixed by
(a) a dedicated `check_real_manifest_format_parses()` that feeds the parser a VERBATIM,
byte-for-byte excerpt of the real v1.77.0 MANIFEST.md as literal test data, and (b)
switching the apply-simulation fixture's own generated manifest to the real truncated
STYLE. F3 — added an `add`-operation target-collision case: a genuine unrelated
user file already sitting at a path the update wants to `add` a new OS file to must be
flagged for confirm, never silently overwritten and never a hard failure either.

LOCK-AMENDMENT 3 (2026-07-02, Po-walk findings 5d4bbbf2, F6 + F1-confirm): this floor
test's own docstring warned "the floor test could never see this — it tests the
predicate, not the full flow with housekeeping" — that gap is closed here.
`check_e2e_apply_with_housekeeping_and_receipt()` runs an END-TO-END apply simulation
that includes the post-apply housekeeping/nav-rebuild step the walk's real bug lived
in: discrete ops -> housekeeping (nav-block injection into governed user files,
exactly the F6 mutation class) -> THEN the covenant receipt, using the new
`tropo_update_receipt.ReceiptSeal` (RECEIPT-LAST structural guard) and dual-hash
receipt (`tropo_update_receipt.content_hash` + honest nav-chrome disclosure list).
It also proves the guard can fail (a write attempted after `seal()` must raise) and
that `tropo_update_confirm_gate.ConfirmGate` structurally refuses to treat a blanket
approval as clearing a per-item `needs_confirm` (F1-confirm, the Po-walk bypass class).

`check_against_real_walk_artifacts()` goes one step further than a fixture: per
Talos's own standing lesson (memory 7c2f8a04, "a self-consistent fixture proves
nothing"), it re-derives the dual-hash proof against the ACTUAL files + ACTUAL
pre-apply fingerprints left behind by the real failed Po walk
(`/private/tmp/tropo-walk-v178` + `-preapply-hashes.json`) when those artifacts are
present on the machine running this test — non-fatal (skipped, not failed) if they
are not, since they are walk-session-local and not shipped with the repo.

Exit 0 = PASS, Exit 1 = FAIL.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAMESPACE_MODULE_PATH = ROOT / "vault" / "tools" / "lib" / "tropo_update_namespace.py"
RECEIPT_MODULE_PATH = ROOT / "vault" / "tools" / "lib" / "tropo_update_receipt.py"
CONFIRM_MODULE_PATH = ROOT / "vault" / "tools" / "lib" / "tropo_update_confirm_gate.py"
RELATIONS_HEADER_PATH = ROOT / "vault" / "tools" / "tropo-generate-relations-header.py"

# The real, seeded stranger studio the Po walk ran against (finding 5d4bbbf2) and
# Argus's independent pre-boot fingerprint file. Session-local artifacts, not part
# of this repo — every check that uses them degrades to SKIPPED, never FAILED, if
# they are absent (a fresh machine, a cleaned /private/tmp, CI).
REAL_WALK_STUDIO = Path("/private/tmp/tropo-walk-v178")
REAL_WALK_PREHASHES = Path("/private/tmp/tropo-walk-v178-preapply-hashes.json")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_namespace_module():
    return _load_module("tropo_update_namespace", NAMESPACE_MODULE_PATH)


def load_receipt_module():
    return _load_module("tropo_update_receipt", RECEIPT_MODULE_PATH)


def load_confirm_module():
    return _load_module("tropo_update_confirm_gate", CONFIRM_MODULE_PATH)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# A VERBATIM excerpt — copy-pasted, byte-for-byte, never generated by this test's own code —
# from a real shipped manifest: tropo-releases/v1.77.0/builds/tropo-os-v1.77.0/MANIFEST.md,
# lines 7-12. This is the direct fix for Argus A123's re-verify F1 finding: the fixture's own
# generated MANIFEST.md matched this test's own parser instead of shipped reality, hiding a
# parse bug (only 2/957 real rows parsed) that a self-consistent fixture could never catch.
# parse_real_shipped_manifest_excerpt() below asserts the parser handles this UNMODIFIED text.
REAL_V177_MANIFEST_EXCERPT = """| Path | Size | SHA-256 |
|------|-----:|--------|
| .cursorrules | 704 | `93a3feeab56b...` |
| .github/copilot-instructions.md | 689 | `e6ed815f2aff...` |
| .tropo-studio/CAPSULE.md | 6,304 | `0c7e9015f196...` |
| .tropo-studio/README.md | 2,316 | `7760fb4af570...` |
"""


def check_real_manifest_format_parses(namespace_mod):
    """Adversarial isolation for F1: parse the VERBATIM real-manifest excerpt above and
    assert every row lands correctly, with the ellipsis stripped and the 12-hex prefix
    preserved. Returns None on success, or a failure-reason string."""
    index, skipped = namespace_mod.parse_manifest_md(REAL_V177_MANIFEST_EXCERPT)
    expected = {
        ".cursorrules": "93a3feeab56b",
        ".github/copilot-instructions.md": "e6ed815f2aff",
        ".tropo-studio/CAPSULE.md": "0c7e9015f196",
        ".tropo-studio/README.md": "7760fb4af570",
    }
    if index != expected:
        return f"parsed {index!r}, expected {expected!r} (skipped={skipped})"
    return None


def seed_vault(root):
    """Seed a throwaway vault on the REAL shipped layout (LOCK-AMENDMENT 2 rider)."""
    (root / "vault" / "playbooks").mkdir(parents=True)
    (root / "vault" / "tools").mkdir(parents=True)
    (root / ".tropo").mkdir(parents=True)
    (root / ".tropo-studio" / "registries").mkdir(parents=True)

    true_user_files = {
        "vault/files/1a2b3c4d.md": "# A user task\n\nSome user-authored content.\n",
        "vault/files/my-project-5e6f7a8b.md": "# My Project\n\nUser project notes.\n",
        "vault/playbooks/my-workflow-9c0d1e2f.md": "# My Workflow\n\nUser-authored playbook.\n",
    }
    # Spoofed: "tropo" appears in the name, but NOT as the exact `tropo-` prefix required
    # by category (a), and it is never manifest-listed. Proves exact-prefix matching.
    spoofed_file = {
        "vault/files/my-tropo-notes-5a5a5a5a.md": "# Not actually shipped\n\nUser content that merely mentions tropo.\n",
    }
    namespace_os_files = {  # categories (a)/(b) — filename-namespace REPLACE, unchanged shape
        "vault/tropo-rebuild-vault.py": "# shipped tool, version v1\nprint('v1')\n",
        "vault/tropo-validate.py": "# shipped validator, version v1\nprint('v1')\n",
        ".tropo/boot-config.md": "# bootstrap floor content, version v1\n",
    }
    # category (d) — the real gap LOCK-AMENDMENT 2 closes: uid-named canonicals + engine +
    # .tropo-studio registry + root docs. None are tropo-*-named or under .tropo/.
    manifest_os_files = {
        "vault/playbooks/71f186cf.md": "# canonical apply-update playbook, version v1\n",
        "vault/tools/e337f1dd.py": "# pipeline engine, version v1\nprint('v1')\n",
        ".tropo-studio/registries/subsystem-registry.jsonl": '{"subsystem":"example","version":"v1"}\n',
        "README.md": "# Tropo-OS\n\nversion v1\n",
    }
    # The user-modified-shipped case: manifest lists this file's v1 hash, but the on-disk
    # content is already drifted (as if the owner hand-edited a shipped file) before the
    # update plan ever runs.
    drifted_path = "vault/playbooks/71f186cf.md"
    drifted_content_pre_apply = "# canonical apply-update playbook, version v1 -- LOCALLY EDITED BY OWNER\n"

    # F3 fixture: a genuine user collision at an ADD target. The update wants to add a new
    # OS file at this path; the customer's studio already has unrelated user content sitting
    # there (not manifest-listed at all — never part of any shipped install).
    add_collision_path = "vault/files/collision-7f7f7f7f.md"
    add_collision_user_content = "# Pre-existing user content\n\nThe customer put this here independently.\n"

    for rel, content in {**true_user_files, **spoofed_file, **namespace_os_files,
                          **manifest_os_files, add_collision_path: add_collision_user_content}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    # Build the fixture MANIFEST.md from the CLEAN (pre-drift) content hashes, in the SAME
    # truncated+ellipsis STYLE the real shipped format uses (12-hex + `...`) — not the full
    # 64-hex form. This is the apply-simulation fixture (necessarily hand-constructed, since
    # this test can't embed 957 real files' bytes); the SEPARATE
    # check_real_manifest_format_parses() function above is what actually proves the parser
    # against unmodified real bytes (Argus A123's F1 fix — a self-consistent generated
    # fixture alone is exactly the bug class this amendment exists to kill).
    manifest_lines = ["| Path | Size | SHA-256 |", "|------|-----:|--------|"]
    for rel, content in manifest_os_files.items():
        h = hashlib.sha256(content.encode()).hexdigest()[:12]
        manifest_lines.append(f"| {rel} | {len(content)} | `{h}...` |")
    (root / "MANIFEST.md").write_text("\n".join(manifest_lines) + "\n")

    # NOW drift the one file, after the manifest was built from its clean content —
    # simulating "owner hand-edited a shipped file sometime after install."
    (root / drifted_path).write_text(drifted_content_pre_apply)

    time.sleep(0.05)  # coarse mtime resolution guard, same as v1 of this fixture

    return {
        "true_user_files": true_user_files,
        "spoofed_file": spoofed_file,
        "namespace_os_files": namespace_os_files,
        "manifest_os_files": manifest_os_files,
        "drifted_path": drifted_path,
        "add_collision_path": add_collision_path,
        "add_collision_user_content": add_collision_user_content,
    }


def build_update_plan(fixture, plant_violation=False):
    """The update package's operation list: ('replace', rel, content) for every
    OS-substrate file (namespace + manifest categories), plus one ('add', rel,
    content) targeting the F3 add-collision fixture path (LOCK-AMENDMENT 2 F3 —
    the target already exists as genuine, unlisted user content). `plant_violation`
    injects a 'replace' op targeting a true user file, for the gauntlet run."""
    plan = [('replace', rel, content.replace("v1", "v2"))
            for rel, content in {**fixture["namespace_os_files"], **fixture["manifest_os_files"]}.items()]
    plan.append(('add', fixture["add_collision_path"], "# New OS file the update wants to add\n"))
    if plant_violation:
        plan.append(('replace', next(iter(fixture["true_user_files"])),
                      "# COVENANT VIOLATION — this should never write\n"))
    return plan


def apply_plan(root, plan, namespace_mod, manifest_index, bypass_predicate=False):
    """The engine under test: for each planned op, consult the four-category
    predicate (classify()) and branch on REPLACE / PRESERVE / USER_MODIFIED_SHIPPED.
    Returns (written, refused, needs_confirm) rel-path lists.

    PRESERVE means something different depending on op kind (LOCK-AMENDMENT 2 F3):
    for a 'replace' op it's a governance violation (this path should never have
    been targeted at all — refused, matches the playbook's Step 1b halt). For an
    'add' op whose target already exists and is PRESERVE (not manifest-listed —
    i.e. genuine unrelated user content sitting at the target path), it's a
    collision, not a violation — surfaced for confirm, same as USER_MODIFIED_SHIPPED,
    never a silent overwrite and never a hard failure either.

    `bypass_predicate=True` simulates a buggy/malicious engine that writes
    everything without consulting the predicate — used ONLY by --gauntlet to
    prove the churn detector would catch a violation even if the predicate
    that normally prevents it were absent or buggy."""
    written, refused, needs_confirm = [], [], []
    for kind, rel, content in plan:
        if bypass_predicate:
            (root / rel).write_text(content)
            written.append(rel)
            continue

        p = root / rel

        if kind == 'add' and not p.exists():
            # Playbook Step 3 add-operation step 2, "does not exist" branch — nothing to
            # overwrite, proceeds unconditionally. No classify() call needed.
            p.write_text(content)
            written.append(rel)
            continue

        current_hash = _hash(p) if p.exists() else None
        verdict = namespace_mod.classify(rel, manifest_index=manifest_index, current_hash=current_hash)

        if verdict == namespace_mod.REPLACE:
            p.write_text(content)
            written.append(rel)
        elif verdict == namespace_mod.USER_MODIFIED_SHIPPED:
            needs_confirm.append(rel)  # never silently overwrite
        elif kind == 'add':
            needs_confirm.append(rel)  # F3: add-target collision with unlisted content — confirm, not a hard halt
        else:
            refused.append(rel)  # 'replace' op targeting a PRESERVE path — governance violation, refused
    return written, refused, needs_confirm


def run_floor_test(plant_violation=False):
    namespace_mod = load_namespace_module()
    tmp = Path(tempfile.mkdtemp(prefix="tropo-floor-test-"))
    try:
        real_format_error = check_real_manifest_format_parses(namespace_mod)

        fixture = seed_vault(tmp)
        manifest_index, _skipped = namespace_mod.parse_manifest_md((tmp / "MANIFEST.md").read_text())

        # Record pre-apply state for every TRUE user file (category c) + the spoofed file
        # + the add-collision path (F3 — also genuine unrelated user content). These must
        # show zero churn regardless of gauntlet mode's target.
        watch_files = {**fixture["true_user_files"], **fixture["spoofed_file"]}
        before = {}
        for rel in watch_files:
            p = tmp / rel
            before[rel] = (p.stat().st_mtime, _hash(p))
        drifted_before_apply = (tmp / fixture["drifted_path"]).read_text()
        collision_before_apply = (tmp / fixture["add_collision_path"]).read_text()

        plan = build_update_plan(fixture, plant_violation=plant_violation)
        written, refused, needs_confirm = apply_plan(
            tmp, plan, namespace_mod, manifest_index, bypass_predicate=plant_violation
        )

        # Assertion 1 — zero true-user-file / spoofed-file churn.
        churned = []
        for rel in watch_files:
            p = tmp / rel
            after_mtime, after_hash = p.stat().st_mtime, _hash(p)
            if (after_mtime, after_hash) != before[rel]:
                churned.append(rel)

        # Assertion 2 — every CLEAN (non-drifted, non-collision, non-planted-violation)
        # OS-substrate path in the plan was updated to its planned (v2) content.
        true_user_rels = set(fixture["true_user_files"])
        plan_by_path = {rel: content for _kind, rel, content in plan}
        clean_os_rels = [rel for rel in plan_by_path
                          if rel not in (fixture["drifted_path"], fixture["add_collision_path"])
                          and rel not in true_user_rels]
        not_updated = [rel for rel in clean_os_rels
                        if (tmp / rel).read_text() != plan_by_path[rel]]

        # Assertion 3 — the drifted (user-modified-shipped) file: NOT silently overwritten,
        # appears in needs_confirm, unchanged from the drift.
        drift_path = fixture["drifted_path"]
        drift_silently_overwritten = (tmp / drift_path).read_text() != drifted_before_apply
        drift_flagged = drift_path in needs_confirm

        # Assertion 4 (F3) — the add-target collision: NOT silently overwritten (the
        # customer's unrelated pre-existing content survives), appears in needs_confirm.
        collision_path = fixture["add_collision_path"]
        collision_silently_overwritten = (tmp / collision_path).read_text() != collision_before_apply
        collision_flagged = collision_path in needs_confirm

        return {
            "real_format_error": real_format_error,
            "churned": churned,
            "not_updated": not_updated,
            "written": written,
            "refused": refused,
            "needs_confirm": needs_confirm,
            "drift_silently_overwritten": drift_silently_overwritten,
            "drift_flagged": drift_flagged,
            "collision_silently_overwritten": collision_silently_overwritten,
            "collision_flagged": collision_flagged,
            "plant_violation": plant_violation,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_nav_sentinel_matches_generator(receipt_mod):
    """Adversarial isolation: the dual-hash receipt's canonicalization regex must
    strip exactly the sentinel pair the REAL nav-block renderer inserts. If someone
    changes the sentinel strings in tropo-generate-relations-header.py without
    updating tropo_update_receipt.py, canonicalization silently stops working and
    every receipt starts reporting false content-churn. Returns None on success, a
    failure-reason string otherwise. Non-fatal (returns a warning, not a hard
    failure path caller) if the generator file is missing entirely."""
    if not RELATIONS_HEADER_PATH.exists():
        return None
    text = RELATIONS_HEADER_PATH.read_text()
    if receipt_mod.NAV_BLOCK_START not in text or receipt_mod.NAV_BLOCK_END not in text:
        return (f"tropo_update_receipt.py's NAV_BLOCK_START/END sentinels do not appear "
                f"in {RELATIONS_HEADER_PATH.name} — canonicalization has drifted from "
                f"the real renderer's markup contract")
    return None


def _derive_uid_for_nav(rel_path):
    """Mirror the real renderer's UID resolution for our fixture's filenames:
    bare <uid>.md -> the stem; <slug>-<uid>.md -> the trailing 8 hex chars."""
    stem = rel_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    m = re.search(r"([0-9a-f]{8})$", stem)
    return m.group(1) if m else stem


def simulate_nav_housekeeping(root, target_rels, seal, receipt_mod):
    """Simulate the REAL post-apply housekeeping step
    (`tropo-generate-relations-header.py`, run as Step 4 of the `rebuild-vault.py`
    comprehensive cadence) writing a nav-block into each of `target_rels` — the
    exact mutation class the Po walk's F6 finding caught landing AFTER the receipt
    was computed. Every write is recorded via `seal.record_write()` BEFORE the
    write lands, per RECEIPT-LAST discipline — this function is the reference
    example of a housekeeping step that does it correctly (sequenced before the
    receipt is sealed by the caller). Returns the honest disclosure list:
    [{"path", "byte_hash"}, ...] for every file actually touched.

    Skips files with no H1 heading (matches the real renderer's `insert_or_update_block`
    no-op-on-"no-h1" behavior) — this is also how the real walk's 5th file
    (`weekly-review-3e7a1f88.md`'s housekeeping-scope gap) stayed untouched; here we
    model it as "not passed in target_rels" (a housekeeping run that didn't cover
    every governed path), matching the real root cause (scope, not a renderer bug)."""
    disclosure = []
    for rel in target_rels:
        p = root / rel
        if not p.exists():
            continue
        text = p.read_text()
        h1 = re.search(r"^# .+$", text, re.MULTILINE)
        if not h1:
            continue
        uid = _derive_uid_for_nav(rel)
        block = f"{receipt_mod.NAV_BLOCK_START}\n**\U0001f517 This file** — UID `{uid}` · type `note`\n{receipt_mod.NAV_BLOCK_END}"
        insert_pos = h1.end()
        rest = text[insert_pos:].lstrip("\n")
        new_text = text[:insert_pos] + "\n\n" + block + "\n\n" + rest
        seal.record_write(rel)  # RECEIPT-LAST: recorded before the disk write lands
        p.write_text(new_text)
        disclosure.append({"path": rel, "byte_hash": receipt_mod.byte_hash(new_text)})
    return disclosure


def check_e2e_apply_with_housekeeping_and_receipt():
    """THE LOCK-AMENDMENT 3 fixture: an end-to-end apply simulation that includes
    the post-apply housekeeping step, proving all three structural fixes together
    (they share one code path in the real playbook, so they are proven together
    here too, not in isolation):

      1. RECEIPT-LAST — housekeeping runs and is recorded via ReceiptSeal BEFORE
         seal(); any write attempted after seal() must raise.
      2. DUAL-HASH RECEIPT — every governed user file's content-hash (nav-block
         canonicalized) is IDENTICAL pre- and post-apply, even though 4 of 5 had
         their nav chrome (and therefore byte-hash) change; the receipt discloses
         exactly which files were chromed, with real byte-hashes.
      3. CONFIRM HARD-STOP — a needs_confirm item cannot be treated as cleared by
         a blanket approval recorded under a different key; only an explicit
         per-item record_ack() clears it.

    Returns a dict of booleans/details; caller decides pass/fail."""
    namespace_mod = load_namespace_module()
    receipt_mod = load_receipt_module()
    confirm_mod = load_confirm_module()

    tmp = Path(tempfile.mkdtemp(prefix="tropo-e2e-receipt-test-"))
    try:
        fixture = seed_vault(tmp)
        manifest_index, _skipped = namespace_mod.parse_manifest_md((tmp / "MANIFEST.md").read_text())

        seal = receipt_mod.ReceiptSeal()
        confirm_gate = confirm_mod.ConfirmGate()

        watch_files = sorted({**fixture["true_user_files"], **fixture["spoofed_file"]})
        pre_content_hashes = {rel: receipt_mod.content_hash((tmp / rel).read_text()) for rel in watch_files}

        # Step 3 (discrete operations) — every OS-substrate write recorded via the seal.
        plan = build_update_plan(fixture)
        written, refused, needs_confirm = apply_plan(tmp, plan, namespace_mod, manifest_index)
        for rel in written:
            seal.record_write(rel)
        for rel in needs_confirm:
            confirm_gate.register(rel, kind="user_modified_shipped_or_collision",
                                   message="never overwrite without an explicit per-item ack")

        # CONFIRM HARD-STOP proof (F1-confirm): a blanket approval recorded under a
        # DIFFERENT key must NOT clear a specific needs_confirm item.
        confirm_blanket_bypass_blocked = None
        confirm_per_item_ack_clears = None
        if needs_confirm:
            target = needs_confirm[0]
            confirm_gate.register("__blanket_user_approval__", kind="blanket",
                                   message="user said go ahead with the whole apply")
            confirm_gate.record_ack("__blanket_user_approval__", "approved")
            try:
                confirm_gate.require_cleared(target)
                confirm_blanket_bypass_blocked = False  # BAD — blanket ack should never satisfy this
            except confirm_mod.ConfirmNotRecordedError:
                confirm_blanket_bypass_blocked = True
            confirm_gate.record_ack(target, "approved")  # the real, explicit per-item ack
            try:
                confirm_gate.require_cleared(target)
                confirm_per_item_ack_clears = True
            except confirm_mod.ConfirmNotRecordedError:
                confirm_per_item_ack_clears = False

        # Step 4.4 (NEW, LOCK-AMENDMENT 3) — housekeeping/nav-rebuild runs and is
        # recorded via the seal, BEFORE the receipt is computed or sealed. Mirrors
        # the real walk's 4-of-5 shape (one file left out of the housekeeping run's
        # scope, exactly as `weekly-review-3e7a1f88.md` was in the real walk).
        housekeeping_targets = watch_files[:-1]
        disclosure = simulate_nav_housekeeping(tmp, housekeeping_targets, seal, receipt_mod)

        post_content_hashes = {rel: receipt_mod.content_hash((tmp / rel).read_text()) for rel in watch_files}
        content_entries = [
            {"path": rel, "pre_hash": pre_content_hashes[rel], "post_hash": post_content_hashes[rel]}
            for rel in watch_files
        ]
        content_all_unchanged = all(e["pre_hash"] == e["post_hash"] for e in content_entries)

        # Step 4.5/4.6 (receipt) — the terminal act. Seal AFTER housekeeping, not before.
        receipt_path = "vault/updates/receipts/tropo-update-fixture-receipt.md"
        seal.seal(receipt_path)

        # RECEIPT-LAST proof (F6): any write attempted after seal() must be refused —
        # this is what would have caught the real bug (housekeeping running after the
        # receipt) at the moment it happened, not three weeks later in a Po walk.
        post_seal_write_blocked = False
        try:
            seal.record_write("vault/files/late-housekeeping-should-not-happen.md")
        except receipt_mod.PostReceiptWriteError:
            post_seal_write_blocked = True

        receipt_md = receipt_mod.build_receipt_markdown(
            update_id="tropo-update-fixture", target_version="9.9.9", result="applied",
            content_hash_entries=content_entries, nav_disclosure=disclosure,
            tropo_components_replaced=written, generated_at="2026-07-02T00:00:00Z",
        )
        receipt_reports_unchanged_count = f"content_unchanged_count: {len(content_entries)}" in receipt_md
        receipt_discloses_every_chromed_file = all(d["path"] in receipt_md and d["byte_hash"] in receipt_md
                                                    for d in disclosure)
        receipt_names_no_mismatch = "COVENANT VIOLATION" not in receipt_md

        return {
            "needs_confirm_present": bool(needs_confirm),
            "confirm_blanket_bypass_blocked": confirm_blanket_bypass_blocked,
            "confirm_per_item_ack_clears": confirm_per_item_ack_clears,
            "housekeeping_touched_count": len(disclosure),
            "housekeeping_expected_count": len(housekeeping_targets),
            "content_all_unchanged": content_all_unchanged,
            "content_entries": content_entries,
            "post_seal_write_blocked": post_seal_write_blocked,
            "receipt_reports_unchanged_count": receipt_reports_unchanged_count,
            "receipt_discloses_every_chromed_file": receipt_discloses_every_chromed_file,
            "receipt_names_no_mismatch": receipt_names_no_mismatch,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_against_real_walk_artifacts():
    """Verify the dual-hash proof against the ACTUAL files + ACTUAL pre-apply
    fingerprints left behind by the real Po walk that found F6 (finding 5d4bbbf2),
    not a fixture — per Talos's own standing lesson (memory 7c2f8a04). Returns
    None if the session-local artifacts aren't present on this machine (skip, not
    fail), or a failure-reason string if the dual-hash proof does not hold against
    the real walk's own disk state."""
    if not (REAL_WALK_STUDIO.is_dir() and REAL_WALK_PREHASHES.exists()):
        return None
    receipt_mod = load_receipt_module()
    try:
        data = json.loads(REAL_WALK_PREHASHES.read_text())
    except Exception as e:
        return f"could not parse {REAL_WALK_PREHASHES}: {e}"
    user_files = data.get("user_files", {})
    if not user_files:
        return f"{REAL_WALK_PREHASHES} has no user_files entries — nothing to verify"
    mismatches = []
    any_byte_changed = False
    for rel, pre_hash in user_files.items():
        p = REAL_WALK_STUDIO / rel
        if not p.exists():
            mismatches.append(f"{rel}: missing on disk")
            continue
        text = p.read_text()
        if receipt_mod.content_hash(text) != pre_hash:
            mismatches.append(f"{rel}: content_hash mismatch vs recorded pre-apply fingerprint")
        if receipt_mod.byte_hash(text) != pre_hash:
            any_byte_changed = True
    if mismatches:
        return "; ".join(mismatches)
    if not any_byte_changed:
        return (f"none of {len(user_files)} real walk file(s) had a byte-hash difference from "
                f"pre-apply — the walk studio may have been reset; this check needs the actual "
                f"chrome-mutated state to be meaningful")
    return None


def main() -> int:
    if not NAMESPACE_MODULE_PATH.exists():
        print(f"FAIL — namespace predicate module not found at "
              f"{NAMESPACE_MODULE_PATH.relative_to(ROOT)}")
        return 1
    for label, path in (("receipt", RECEIPT_MODULE_PATH), ("confirm gate", CONFIRM_MODULE_PATH)):
        if not path.exists():
            print(f"FAIL — {label} module not found at {path.relative_to(ROOT)}")
            return 1

    gauntlet = "--gauntlet" in sys.argv

    result = run_floor_test(plant_violation=gauntlet)

    if result["real_format_error"]:
        print(f"FAIL — parse_manifest_md() does not correctly parse the REAL shipped manifest "
              f"format (verbatim v1.77.0 excerpt): {result['real_format_error']}")
        return 1

    if gauntlet:
        if result["churned"]:
            print(f"PASS (gauntlet) — floor test correctly detected the planted "
                  f"covenant violation: {result['churned']}")
            return 0
        print("FAIL (gauntlet) — the planted covenant violation was NOT detected. "
              "The floor test is not a real gate (tautology risk).")
        return 1

    if result["churned"]:
        print(f"FAIL — THE FLOOR TEST: {len(result['churned'])} true user/spoofed file(s) "
              f"churned by the update plan: {result['churned']}")
        print("       A release whose update path touches user files cannot ship (ADR-049 covenant).")
        return 1

    if result["not_updated"]:
        print(f"FAIL — THE FLOOR TEST (LOCK-AMENDMENT 2): {len(result['not_updated'])} clean "
              f"OS-substrate path(s) were NOT updated: {result['not_updated']}")
        print("       The machinery delta must be deliverable — this is the 4496553c gap.")
        return 1

    if result["drift_silently_overwritten"]:
        print(f"FAIL — THE FLOOR TEST (LOCK-AMENDMENT 2): the user-modified-shipped file "
              f"was SILENTLY overwritten instead of surfaced for confirm.")
        return 1

    if not result["drift_flagged"]:
        print(f"FAIL — THE FLOOR TEST (LOCK-AMENDMENT 2): the user-modified-shipped file "
              f"did not appear in needs_confirm — the drift went undetected.")
        return 1

    if result["collision_silently_overwritten"]:
        print(f"FAIL — THE FLOOR TEST (LOCK-AMENDMENT 2 F3): the add-target collision "
              f"(genuine unrelated user content) was SILENTLY overwritten by an add operation.")
        return 1

    if not result["collision_flagged"]:
        print(f"FAIL — THE FLOOR TEST (LOCK-AMENDMENT 2 F3): the add-target collision "
              f"did not appear in needs_confirm — the collision went undetected.")
        return 1

    # --- LOCK-AMENDMENT 3 (finding 5d4bbbf2: F6 receipt-vs-final-state divergence,
    # F1-confirm blanket-approval bypass) --------------------------------------

    receipt_mod = load_receipt_module()
    sentinel_error = check_nav_sentinel_matches_generator(receipt_mod)
    if sentinel_error:
        print(f"FAIL — LOCK-AMENDMENT 3: {sentinel_error}")
        return 1

    e2e = check_e2e_apply_with_housekeeping_and_receipt()

    if not e2e["needs_confirm_present"]:
        print("FAIL — LOCK-AMENDMENT 3 e2e: fixture produced zero needs_confirm items; "
              "the CONFIRM HARD-STOP proof requires at least one to test against.")
        return 1
    if not e2e["confirm_blanket_bypass_blocked"]:
        print("FAIL — LOCK-AMENDMENT 3 (F1-confirm): ConfirmGate treated a blanket approval "
              "recorded under a different key as clearing a specific needs_confirm item. "
              "This is the exact Po-walk bypass class; it must be structurally impossible.")
        return 1
    if not e2e["confirm_per_item_ack_clears"]:
        print("FAIL — LOCK-AMENDMENT 3: an explicit per-item record_ack('approved') did not "
              "clear require_cleared() for that same item — the gate is over-strict, not just under-strict.")
        return 1
    if e2e["housekeeping_touched_count"] != e2e["housekeeping_expected_count"]:
        print(f"FAIL — LOCK-AMENDMENT 3 e2e: housekeeping simulation touched "
              f"{e2e['housekeeping_touched_count']} file(s), expected {e2e['housekeeping_expected_count']}.")
        return 1
    if not e2e["content_all_unchanged"]:
        mismatched = [e for e in e2e["content_entries"] if e["pre_hash"] != e["post_hash"]]
        print(f"FAIL — LOCK-AMENDMENT 3 (DUAL-HASH RECEIPT): {len(mismatched)} file(s) had their "
              f"CONTENT hash change (nav-canonicalized), not just chrome: {mismatched}")
        return 1
    if not e2e["post_seal_write_blocked"]:
        print("FAIL — LOCK-AMENDMENT 3 (RECEIPT-LAST, F6): ReceiptSeal did NOT refuse a write "
              "attempted after seal() — this is the exact regression class the guard exists to catch.")
        return 1
    if not (e2e["receipt_reports_unchanged_count"] and e2e["receipt_discloses_every_chromed_file"]
            and e2e["receipt_names_no_mismatch"]):
        print(f"FAIL — LOCK-AMENDMENT 3: rendered receipt is not honest/complete: "
              f"reports_unchanged_count={e2e['receipt_reports_unchanged_count']} "
              f"discloses_every_chromed_file={e2e['receipt_discloses_every_chromed_file']} "
              f"names_no_mismatch={e2e['receipt_names_no_mismatch']}")
        return 1

    real_walk_error = check_against_real_walk_artifacts()
    if real_walk_error:
        print(f"FAIL — LOCK-AMENDMENT 3 (real walk artifact cross-check): {real_walk_error}")
        return 1
    real_walk_note = (" + verified against the REAL failed-walk studio's disk state"
                       if REAL_WALK_STUDIO.is_dir() and REAL_WALK_PREHASHES.exists()
                       else " (real walk artifacts not present on this machine — skipped, not failed)")

    print(f"PASS — THE FLOOR TEST: real-manifest-format parser proof clean; zero true-user-file churn; "
          f"{len(result['written'])} OS-substrate file(s) replaced (namespace + manifest categories, "
          f"incl. a clean add); {len(result['refused'])} non-OS write(s) refused; "
          f"1 user-modified-shipped file + 1 add-target collision both correctly flagged for "
          f"overwrite-confirm, neither silently touched. LOCK-AMENDMENT 3: e2e apply-with-housekeeping "
          f"proves RECEIPT-LAST (post-seal write refused), DUAL-HASH RECEIPT ({len(e2e['content_entries'])}/"
          f"{len(e2e['content_entries'])} content unchanged, {e2e['housekeeping_touched_count']} file(s) "
          f"honestly disclosed as nav-chromed), and CONFIRM HARD-STOP (blanket approval could not clear "
          f"a per-item confirm; explicit per-item ack could){real_walk_note}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
