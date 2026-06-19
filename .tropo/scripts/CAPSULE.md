---
spec_version: 2
tier: capsule
folder_type: governed
owner: argus
write_access: [argus, talos, vela]
read_access: all
purpose: "Tropo-OS kernel scripts — ship with every release. Python, domain-general Tropo-OS capabilities."
uid: 4c2a8f39
created: 2026-04-20
created_by: vela-v31
governed_by_convention: ".tropo/scripts/ is one of three scripts/ locations in the Tropo ecosystem; see §Cross-references."
---

# `.tropo/scripts/` — Tropo-OS Kernel Scripts

## Purpose

Python scripts that **are part of Tropo-OS itself** and ship with every release. When a release is cut, this folder is copied into `releases/<version>/builds/.../.tropo/scripts/` and ends up in every user's vault.

These are domain-general capabilities that any Tropo-OS vault needs, not Argo-specific utilities.

**v1.5 user-shipped toolchain (the scripts users run by hand):**

- [`rebuild-vault.py`](rebuild-vault.py) — regenerates `vault/00-index.jsonl` + `00-project-tree.jsonl` from `vault/files/<uid>.md` frontmatter. Cleans stale `00-cascade-<uid>.jsonl` files. Run after hand-editing a ledger entry.
- [`tropo-validate.py`](tropo-validate.py) — structural validator: AGENTS.md coverage, cross-reference resolution, UID consistency, integrity parity. Read-only.
- [`validate-no-absolute-paths.py`](validate-no-absolute-paths.py) — vault portability validator. Both regular-mode (allowlist) and `--strict` (release-gate).
- [`rehydrate.py`](rehydrate.py) — regenerates `00-tropo-nav/` symlink tree from the Vault. Relocated 2026-04-20 from `argo-os/scripts/` per Argus A28's architectural call.
- [`rebuild-project-index.py`](rebuild-project-index.py) — rebuilds a single project's `00-index.md` from folder contents.

See [vault/files/a24c5b66.md](../kb/how-to-maintain-your-vault.md) for when to run each.

**Argo-only release-pipeline scripts (NOT shipped to user vaults — `extraction_scope: argo-reference`; user vaults will not see these in their `.tropo/scripts/` directory):**

- `build-release.py` — assembles a Tropo-OS release from the Argo source vault. Argo-only; users do not build Tropo releases from their own vault.
- `register-kernel.py` — kernel-file registration migration utility (Argo-internal).

These appear in the Argo source vault's `.tropo/scripts/` for Argo's own release workflow but are filtered out at build time per `KERNEL_EXCLUDE_PATTERNS` in `build-release.py` itself. If you're a user reading this in a downloaded vault and don't see these scripts in your `.tropo/scripts/` directory — that's correct.
- **General Tropo-OS utilities** — anything any Tropo-OS vault (not just Argo) would need.

## What does NOT belong here

- **Vault-admin-tier helpers** — those live at `argo-os/.tropo-studio/scripts/` (board renderers, ad-hoc vault utilities). If a script is only useful for this vault's internal workflow and never a general Tropo-OS capability, it's not kernel-tier.
- **Engineering repo tooling** — those live at repo-root `/scripts/` (TypeScript, called via `npm run <name>`). The repo toolchain for the Next.js app is separate from the OS kernel.
- **Scripts that hardcode absolute paths** — kernel scripts must be portable. Any vault on any machine should be able to run them. See [rehydrate.py](rehydrate.py) for the vault-root resolution pattern (explicit arg → walk up → cwd fallback, never hardcoded).

## Write access

- **Argus** — Chief Architect, owns `.tropo/` kernel.
- **Talos** — Lead Engineering Swarm, on hold currently; when active, writes code that lives here.
- **Vela** — vault admin delegate; writes/edits with architectural approval for ops-adjacent scripts (e.g., today's rehydrate.py move).

Changes here require architectural review because they ship in every release.

## Governance rules

1. **Portable.** No hardcoded absolute paths. Resolve vault root via argument or walk-up for `settings/env.md`. If resolution fails, raise with a clear error — never silently default.
2. **Python.** Kernel scripts are Python 3. The engineering repo's TS scripts at `/scripts/` don't belong here; they're a different layer.
3. **Ship-ready.** Every script here ends up in user vaults on the next release cut. Write for a stranger, not for Argo.
4. **Fail loud on declared-but-unreachable.** Per the v2.2 boot playbook Tier Reachability rule and [ADR-032](../../vault/files/e6c3f410.md) 2026-04-20 amendment: if a script declares a dependency exists, it should throw on missing — not silently skip. See [`.tropo/scripts/rebuild-vault.py`:608](../../../`.tropo/scripts/rebuild-vault.py`) for the pattern.
5. **Documented.** Every script's docstring declares: what it does, inputs, outputs, where it's called from, what it depends on.
6. **Verify against canonical L0 registry before mutating `member_of:`.** Per [Operating Principle 11](../../.tropo-studio/operating-principles.md#11-verify-against-canonical-reference-before-architectural-calls), any kernel script that mutates a project's `member_of:` array MUST consult [`.tropo-studio/registries/canonical-l0-projects.yaml`](../../.tropo-studio/registries/canonical-l0-projects.yaml) first. If the target project's UID appears in `canonical_l0_projects` or `non_l0_with_hub_only_risk`, the mutation requires explicit Mike approval before the script runs. The pre-flight gate ([`validate-canonical-l0.py`](validate-canonical-l0.py)) catches drift after the fact; this rule is the discipline that prevents drift in the first place. Mirrors Rule 6 in [`.tropo-studio/scripts/CAPSULE.md`](../../.tropo-studio/scripts/CAPSULE.md). **Why:** v1.12 substrate-membership backfill replaced empty `member_of: []` with hub-UIDs without distinguishing "missing parent" from "true L0 root" — collapsed the rendered nav. v1.13.5 closed the symptom; this rule closes the cause.

## Validator Check Pattern (v1.38.0)

*Canonical guidance for authoring new check functions in `tropo-validate.py`. Authored at v1.38.0 ship per the cycle that audited all 35 checks (inventory at [`vault/files/391043ad.md`](../../vault/files/391043ad.md)).*

### Two safe patterns; one forbidden anti-pattern

When implementing a new check that reads vault entry frontmatter:

**Pattern A — `yaml.safe_load` + dict-key lookup.** Best for checks that read multiple fields, traverse nested structure, or need typed value comparison.

```python
fm_text = split_frontmatter(file_path.read_text())
if fm_text is None:
    continue
try:
    fm = yaml.safe_load(fm_text)
except yaml.YAMLError:
    continue
if not isinstance(fm, dict):
    continue
# Use dict-key lookup
if fm.get("required_field") is None:
    issues.append(...)
```

**Pattern B — `split_frontmatter` + `get_scalar` (the existing helper in tropo-validate.py).** Best for checks that read a **single top-level scalar field** and want lightweight regex-based extraction. `get_scalar` is field-aware: line-anchored regex (`^{field}:\s*(.*)$`), quote-aware, comment-aware. Safe against nested-field collision.

```python
fm_text = split_frontmatter(file_path.read_text())
if fm_text is None:
    continue
value = get_scalar(fm_text, "required_field")
if value is None:
    issues.append(...)
```

**Pattern A vs. Pattern B chooser (per R3 sa.skeptic-099 P1-1 + R4 sa.cold-boot-197 P1 absorption):**

- **Use Pattern A when** the check reads list-valued fields, nested dict fields, multiple fields requiring typed comparison, OR fields that require structural validation (well-formedness, type coercion, recursive walks).
- **Use Pattern B when** the check reads a single top-level scalar field for presence/absence/value-equality.
- **`get_scalar` is scalar-only** — for list-valued fields it returns either `None` or the first line's truncated content. Do NOT use Pattern B for lists; use Pattern A + dict iteration.

**Forbidden — Pattern C: any non-line-anchored test against the raw `fm_text` string.**

```python
# NEVER DO ANY OF THESE
if "field_name:" in fm_text:                  # substring-match — collides with nested fields
    ...
if re.search(r'field_name', fm_text):         # regex without ^-anchor — same defect class
    ...
if "field_name" in fm_text.lower():           # case-folded substring — same defect class
    ...
```

The forbidden boundary (per R3 sa.skeptic-099 P1-2 absorption): **any test against `fm_text` that is not either (a) parsed via `yaml.safe_load` into a dict + dict-key lookup, or (b) extracted via `get_scalar` or a line-anchored regex with explicit `^` start-of-line marker**. The defect class is "field-name match that doesn't distinguish top-level field from nested key" — substring-match, non-anchored regex, and case-folded substring all fall into it.

Why forbidden: nested-field collision causes false positives. Example: Argus's charter has `soul.role:` as a nested key. A check that tested `"role:" in fm_text` returned True (the substring exists in the nested key), so a missing top-level `role:` field would silently PASS. This bug existed in `check_charter_conformance` until v1.37.0 R3 caught it.

### Prior art

- **v1.37.0 R3:** sa.skeptic-095 caught the substring-match bug in `check_charter_conformance`. The check was refactored to Pattern A in-cycle. WARN count rose 31 → 43 — honest surfacing of pre-existing substrate drift that the buggy check had been silently passing.
- **v1.38.0:** substrate-wide audit of all 35 checks. Zero additional Pattern C bugs found beyond the v1.37.0 R3 fix. Audit document at [`vault/files/391043ad.md`](../../vault/files/391043ad.md). `check_generation_logs` retired at this cycle (substrate it validated was archived at v1.21.0; zero forward value).

### Check function mechanics (per R4 sa.cold-boot-197 absorption)

The pattern snippets above show parsing safety — they assume the surrounding mechanics. For a fresh check author, the full check function shape:

**Signature contract.** Every check function returns one of:
- `tuple[list[str], int, int]` — `(findings, files_checked, defects_count)` — most common shape
- `tuple[list[str], int]` — `(findings, files_checked)` — for checks without a defect-count distinction
- `tuple[list[str], bool]` — `(findings, ok)` — for binary parity checks

Mirror an existing check at a comparable line number — e.g., `check_pipeline_activation_provenance` for typing/provenance checks; `check_uid_consistency` for identity checks.

**Iteration substrate.** Default: walk `vault/files/*.md`:

```python
files_dir = vault / 'vault' / 'files'
for f in sorted(files_dir.glob('*.md')):
    ...
```

Some checks walk other substrate (`vault.rglob('.tropo-studio')` for sidecars; reads `vault/00-index.jsonl` for index checks). Match the substrate to what the check actually validates.

**Severity choice.**
- **FAIL** — governance invariant violations (ADR-016, ADR-028, broken cross-references, duplicate YAML keys). Block ship.
- **WARN** — conformance drift the substrate should rev toward (per-agent charter conformance; nav-block render-safety). Surface for honest-rev work; do not block ship.
- **INFO** — diagnostic info that distinguishes states (e.g., "exists on disk but not in index → run vault:rebuild"). Surface; do not count toward defects.

**Registration.** After authoring, wire the check into the runner in `main()` at the bottom of `tropo-validate.py`. Find the existing block for the closest-related check and add an adjacent block — print a section header, call the check, count passes/fails/warnings, show truncated findings (`findings[:10]` + ellipsis if more).

### Verification

After adding or refactoring a check, run:

```
npm test -- --verbose
```

This shows per-check PASS/FAIL/WARN distribution. Verify the new check shows expected behavior on known-good substrate AND surfaces real defects on substrate the check is meant to catch.

### When to update the inventory

The inventory at [`vault/files/391043ad.md`](../../vault/files/391043ad.md) is the canonical reference for the 35-check landscape. When adding a new check, append an entry to the inventory per the schema in spec §1.2; bump `check_count_at_audit:` in the inventory frontmatter; document parser pattern + bug-risk + asserts + severity + fields inspected + nesting risk + overlap + disposition.

The inventory is the source of truth for "what checks exist + how they're implemented." Future authors consult it before adding a 36th check.

---

## Cross-references

- **Repo-root [/scripts/](../../../scripts/CAPSULE.md)** — TypeScript engineering tooling for the tropo-ai repo (Next.js app, build scripts). Called via `npm run <name>`. Different domain; does not ship with Tropo-OS releases.
- **[argo-os/.tropo-studio/scripts/](../../.tropo-studio/scripts/CAPSULE.md)** — Vault-admin-tier Python helpers. Board renderers, navigation utilities. Vault-only; does not ship with Tropo-OS releases. **Relocated 2026-04-20 from `argo-os/scripts/`** to mirror the three-tier boot architecture ([ADR-032](../../vault/files/e6c3f410.md)).

The three-location + three-tier model was clarified 2026-04-20 by Argus A28 + Vela V31 + Mike Maziarz in Vault Ops v1.2 cycle follow-on work.

---

*`.tropo/scripts/` CAPSULE v1.0 | Vela V31 | 2026-04-20*
*"Kernel-tier. Ships with every release. Python. Portable. Fail loud."*
