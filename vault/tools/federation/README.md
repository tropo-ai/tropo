# Federation — Phase D enforcement reference implementations

*Reconstructed + re-verified by Metis G86, 2026-07-03. These restore the proof that was lost when the
original same-file-spike scratch was cleaned (the build spec [304badf7](../../files/304badf7.md) §4 flagged
this honesty gap; this dir closes it). Requirements + proven behavior: the same-file spike result
[39df3124](../../files/39df3124.md).*

## What's here

| File | Role |
|---|---|
| `tropo_merge.py` | The **field-aware 3-way git merge driver** for governed markdown (Phase D2). Merges YAML frontmatter field-by-field so INDEPENDENT fields on adjacent lines (`status` vs `owner`) auto-compose instead of false-conflicting; delegates the prose body to `git merge-file`; emits a true field clash as a **parseable `# TROPO-FIELD-CONFLICT` annotation** (never raw `<<<<<<<` markers) and exits non-zero. |
| `tropo_validate_governed.py` | The **mandatory governance-validator GATE** (Phase D3). exit 0=VALID, 1=BROKEN, 2=NEEDS-RESOLUTION. Checks: no conflict markers, single parseable YAML frontmatter, no duplicate keys, required keys present (uid/type/title/owner), non-empty body, filename↔uid agreement, unresolved-annotation detection. **The load-bearing piece** — the driver is necessary but not sufficient (it honors a delete of a required field as a clean merge; the gate catches it). |
| `test_corruption_suite.sh` | The re-runnable red-test corpus. `bash test_corruption_suite.sh` → **9 passed, 0 failed** (6 base + 3 adversarial-break regressions). |

## Adversarial-hardened

A fresh-eyes break pass (2026-07-03) **cracked the first cut** and found two integrity bugs the 6-row suite missed — both now fixed and regression-tested (rows `break1`–`break3`):
- **CRITICAL (fixed):** a `---` line *inside* a multi-line value (a Markdown rule in a `summary:`/`description:` block) was mistaken for the closing frontmatter fence, silently amputating fields below it — and because the driver and validator shared the `.strip()` flaw, the corrupt file was blessed VALID. Fix: exact-line fence detection (`line.rstrip() == "---"`) in **both** tools in lockstep + a stray-fence check in the gate.
- **HIGH (fixed):** two studios appending different items to a `refs:` list destroyed the whole list and the annotation lied (`ours='' theirs=''`). Fix: **element-wise list merge** — the canonical case now auto-merges to the union (all items survive), which is the correct behavior.
- **LOW (fixed):** a legitimate value containing the literal string `TROPO-FIELD-CONFLICT` forced a false HOLD. Fix: line-based detection of the annotation *form*, not a raw substring scan.

## Status

**Reference / spec-proof, not yet production.** These are the de-risking artifacts for the build spec.
They are NOT wired into any live studio. Productionizing them (packaging into the studio bootstrap,
the pre-receive/CI gate, hardening) is **Argus's L1v3 Phase D**. The value here: the behavior is proven
by running (not described), and the exact 3-way semantics + the gate's checks are code Argus can build from.

## Wiring (documented for the build; do not run against a live studio yet)

```
# in a team repo's .gitattributes:
files/*.md merge=tropo
# per clone (studio bootstrap installs this — .gitattributes alone does NOT carry the command):
git config merge.tropo.driver "python3 vault/tools/federation/tropo_merge.py %O %A %B %P"
# the gate as a pre-commit / pre-receive hook (or required CI check):
python3 vault/tools/federation/tropo_validate_governed.py <changed files>
```

## The corruption suite (what's proven)

| Case | Merge | Gate | Meaning |
|---|---|---|---|
| adjacent independent fields (status \| owner) | clean | VALID | the false-conflict killer — the decisive win |
| same field clash (status \| status) | conflict | HOLD | parseable annotation, no raw markers, blocks commit |
| delete required field vs change (owner \| status) | clean | **BROKEN** | driver honors delete; **gate catches the dropped required field** |
| same field clash (title \| title) | conflict | HOLD | same as above |
| disjoint body paragraphs | clean | VALID | prose line-merges fine |
| same body paragraph | conflict | BROKEN | real body conflict; gate blocks the markers |

*The honest guarantee: driver + gate TOGETHER keep a governed file always valid-or-explicitly-in-conflict — never silently broken.*
