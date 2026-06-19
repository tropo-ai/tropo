---
uid: 0aefe71d
type: document
subtype: substrate-doctrine
title: Deletion Discipline — Substrate Preservation Doctrine
description: 'Canonical substrate doctrine entry for the ban-on-rm + use-tropo-recycle.py discipline. Single source of truth — tier-specific amendments at .tropo/SELF-HEALING.md + .tropo-studio/operating-principles.md + vault/AGENTS.md + .tropo-studio/memory/MEMORY.md all reference this entry rather than duplicating content (A68 canonical-content-doctrine). Authored at v1.40.0 ship 2026-05-17 by argus-a70 per Mike-A70 directive. Triggered by: (1) v1.35.0 critical incident (rm bash pattern lost load-bearing brief + spec); (2) Mike-A70 audit 2026-05-17; (3) Talos T8 commit 7a8df68 same-day bypass.'
status: published
state: active
version: '1.0'
locked_at: 2026-05-17
locked_by: argus-a70
owner: tropo
governance_tier: os
governs: All destructive operations on governed substrate at vault/files/<uid>.md (and adjacent governed folders by extension)
applies_to: all-agents
author: argus-a70
created: 2026-05-17
created_by: argus-a70
modified: 2026-05-25
modified_by: orpheus-o11
v1_0_narrative_extension_note: "v1.0 narrative extension 2026-05-25 by orpheus-o11 during v1.53 D2.d (doc-pipeline activation c7a26c5a; doc-spec c660ec29). Added 3 new Composes With rows (Workbench Surface Visibility 3c02f3b7 + doc-pipeline 5a4337ff + publish.pipeline sentinel 7e3a91c8 §6) + new §Composition with Substrate-Preservation Architecture section naming the wider 5-tier pattern (filesystem soft-delete + frontmatter supersession + git sentinel + index pre-check + memory archival). Schema unchanged; narrative-only amendment per Argus A83 D2.d directive."
schema_version: 2
extraction_scope: ship
signed_by: mike-maziarz
signed_at: 2026-05-17
governed_by: 8dd772a0
aligned_with:
- db0fd9b1
- a4f9e2b1
related_substrate:
- agents/argus/.tropo-capsule/memory/entries/6bbb625b.md
- .tropo/scripts/tropo-recycle.py
- .tropo/orientation.md
member_of:
- 2f34d5f8
tags:
- substrate-doctrine
- deletion-discipline
- ban-on-rm
- soft-delete-via-recycle
- every-agent-every-studio
- mike-signed
- canonical-source-of-truth
- v1-40-0
subsystem_hub:
- 8dd772a0
capsule_version: '2.5'
---

# Deletion Discipline — Substrate Preservation Doctrine

<!-- nav-block:start -->
**📍 Vault Path:** [tropo-subsystems](aae9a37b.md) → [Tropo Governance](8dd772a0.md) → **Deletion Discipline — Substrate Preservation Doctrine**

**🌳 Tropo-Nav Path** (VS Code): [../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.40.0 — Deletion Discipline Doctrine (Comprehensive Multi-Tier Codification) Cycle Activation Root/0aefe71d — Deletion Discipline — Substrate Preservation Doctrine.md](../../00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.40.0%20%E2%80%94%20Deletion%20Discipline%20Doctrine%20%28Comprehensive%20Multi-Tier%20Codification%29%20Cycle%20Activation%20Root/0aefe71d%20%E2%80%94%20Deletion%20Discipline%20%E2%80%94%20Substrate%20Preservation%20Doctrine.md)

**🌳 Tropo-Nav Path** (chat): [argo-os/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.40.0 — Deletion Discipline Doctrine (Comprehensive Multi-Tier Codification) Cycle Activation Root/0aefe71d — Deletion Discipline — Substrate Preservation Doctrine.md](argo-os/00-tropo-nav/00-tropo-all/tropo-work/dev-pipeline/v1.40.0%20%E2%80%94%20Deletion%20Discipline%20Doctrine%20%28Comprehensive%20Multi-Tier%20Codification%29%20Cycle%20Activation%20Root/0aefe71d%20%E2%80%94%20Deletion%20Discipline%20%E2%80%94%20Substrate%20Preservation%20Doctrine.md)

**🔗 This file** — UID `0aefe71d` · type `document` · state `active` · status `published`

**↔ Siblings (2):**
  - **under [v1.40.0 — Deletion Discipline Doctrin...](2f34d5f8.md):** [Tropo-OS v1.40.0 — Deletion Discipline Doctrine...](8c9962a7.md) · [Tropo-OS v1.40.0 — Deletion Discipline Doctrine...](8f94abbd.md)

**📥 Cited by (8):**
- [tropo-recycle should check inbound refs before recycling — the...](2784b2d8.md) — `2784b2d8` (type `note`, via `refs`)
- [P0 CLOSED — the silent file-deleter (substrate-loss bug): root...](770b32cb.md) — `770b32cb` (type `note`, via `refs`)
- [Tropo-OS v1.41.0 — Ship v1.40 Properly (Block 4 Hardening Cycl...](800c3352.md) — `800c3352` (type `design-brief`, via `aligned_with`)
- [Tropo-OS v1.40.0 — Deletion Discipline Doctrine (Multi-Tier Co...](8c9962a7.md) — `8c9962a7` (type `release`, via `foundation`, `capabilities_touched`)
- [Tropo Test Harness](952f3aa3.md) — `952f3aa3` (type `project`, via `aligned_with`)
- *+ 3 more — full back-link sweep via `grep -l "0aefe71d" vault/files/*.md`*
<!-- nav-block:end -->

**Relations**

| Relation | Target |
|---|---|
| Governed by | [Tropo Governance (8dd772a0)](8dd772a0.md) |
| Member of | [v1.40.0 — Deletion Discipline Doctrine (Comprehensive Multi-Tier Co... (2f34d5f8)](2f34d5f8.md) |

*Authoritative substrate declaration. Single source of truth. Tier-specific amendments at SELF-HEALING.md + operating-principles.md + vault/AGENTS.md + vault-level memory reference this entry; they do not duplicate content.*

---

## The Doctrine

**Never destroy governed substrate. Always soft-delete.**

When you need to remove a file from `vault/files/` (or any governed folder where destructive operations are possible), the canonical gesture is:

```
python3 .tropo/scripts/tropo-recycle.py <uid> [<uid> ...] --reason "<brief rationale>"
```

This moves the target(s) from `vault/files/<uid>.md` to `recycle/agent-deletions/<YYYY-MM-DD>/<uid>.md` with a log entry. Recovery is `mv` back from `recycle/` to `vault/files/`.

**Never use** `rm`, `rm -*`, `find ... -delete`, `git rm` against `vault/files/<uid>.md` paths. Never pipe `grep -l` output to `xargs rm`. Never bypass the recycle gesture even when:
- The file is already-archived / superseded (still soft-delete)
- The deletion is a "cleanup" / "purge" / "zombie removal" (still soft-delete)
- The principal has approved the deletion (still soft-delete)
- The content is recoverable from git history (still soft-delete)

The discipline is the **process**, not the **outcome**. Soft-delete preserves a recovery path that doesn't require git-revert + commits + downstream re-syncs. It also produces a paper trail (`recycle.log` + dated subfolders) that makes "what happened to substrate X" answerable without git archaeology.

---

## Why the Doctrine Exists

**Three incidents have demonstrated the cost of bypassing the discipline:**

**v1.35.0 critical incident (Argus).** Bash pattern `grep -l <keyword> | xargs rm` deleted load-bearing brief + spec because the keyword matched files describing the feature the keyword named. Substrate was recovered from git history with effort; without git the loss would have been permanent. Led to authoring `tropo-recycle.py` as the canonical soft-delete tool + Argus's personal memory pin.

**Mike-A70 substrate-coverage audit 2026-05-17.** Mike asked whether the ban-on-rm doctrine was clear at multiple levels. Audit answer: doctrine lives in 3 surfaces (tool docstring + orientation row + Argus's memory) + is MISSING from 6 load-bearing governance surfaces. Conclusion: NO, not 100% clear.

**Talos T8 commit `7a8df68` (2026-05-17; same day as the audit).** A freshly-booted Talos T8 directly `rm`'d two zombie kb-articles (60228176 How Tropo Work Works + d0480821 How Tasks Work), bypassing `tropo-recycle.py`. The files were superseded redirect stubs; content-wise no loss; Mike approved. But the **process was wrong** — files are not in `recycle/agent-deletions/2026-05-17/`; no soft-delete paper trail; Talos T8 reached for `rm` because the substrate hadn't told him about `tropo-recycle.py`. The fresh-agent reach-for-rm pattern that the audit predicted within hours.

These three incidents share one pattern: an agent operating in good faith executed a destructive primitive because the doctrine wasn't where the agent looked.

---

## The Discipline at Multiple Tiers

Doctrine doesn't work if it lives in one place. Per v1.40.0 codification:

**OS-tier** ([`.tropo/SELF-HEALING.md`](../../.tropo/SELF-HEALING.md) §Preservation Discipline) — every Tropo agent in every Studio internalizes this at Group 2 of activation. The Self-Healing Primitive covers "fix what you see"; this is the inverse-vector primitive — "preserve what you don't recognize." Same posture, opposite direction.

**Studio-tier** ([`.tropo-studio/operating-principles.md`](../../.tropo-studio/operating-principles.md) Principle 13 — Substrate Preservation Discipline) — Studio-specific operationalization of the OS-tier primitive. Read at every boot by every agent.

**Folder-tier** ([`vault/AGENTS.md`](../../vault/AGENTS.md) §Deletion Discipline) — the governance contract every agent reads before writing or modifying `vault/files/`. The most-read surface for the protected folder.

**Memory-tier** ([`.tropo-studio/memory/MEMORY.md`](../../.tropo-studio/memory/MEMORY.md) → vault-level deletion-discipline entry) — vault-level memory all agents inherit at boot per Tier 2 boot extension. Elevates Argus's personal pin to crew-wide doctrine.

**Canonical source-of-truth (this entry)** — every tier amendment cross-references THIS entry rather than restating the doctrine. A68 canonical-content-doctrine pin honored.

---

## What Counts as a Destructive Operation

This doctrine applies to:

- `rm <path>` (any form, including `-r`, `-f`, `-rf`)
- `find ... -delete`
- `git rm <path>` (git's destructive companion to plain `rm`)
- Piping any path-producing command (`grep -l`, `ls`, `find`, etc.) to `xargs rm` or similar
- Any Python/shell pattern that uses `os.remove`, `Path.unlink`, `shutil.rmtree`, etc. against governed content
- Programmatic clean-up scripts that delete vault entries without going through `tropo-recycle.py`
- **`mv` to a destination outside `recycle/`** (per sa.skeptic-101 P1-2 absorption v1.40.0) — `mv` is exempted ONLY for the recycle gesture itself; moving substrate to `/tmp/`, a workspace folder, or any non-recycle path loses the paper trail and is destruction-by-relocation
- **Shell truncation** (`> path`, `: > path`, `tee path < /dev/null`, redirection patterns that empty content) — destroys content without removing the file; passes any path-existence audit while leaving the file an empty husk; equivalent severity to `rm`

This doctrine does NOT apply to:

- `mv` within recycle (the canonical soft-delete gesture)
- Operations on files outside governed folders (workspace scratch, build artifacts, `.tropoignore`-listed paths)
- Reads (the entire read surface is non-destructive)
- Edits in place (use Edit/Write tools; substrate IS modifiable, just not destructible without recycle)

## Scope — Which Folders the Doctrine Covers

Per sa.cold-boot-198 P1 absorption v1.40.0 — explicit folder enumeration closes the "adjacent governed folders" ambiguity. A fresh agent reads this table at point-of-action:

| Path | Doctrine applies | Rationale |
|---|---|---|
| `vault/files/<uid>.md` | **YES (load-bearing)** | The substrate the canonical tool was authored for; v1.35.0 + Talos T8 incidents both occurred here |
| `vault/00-*.jsonl` (index files) | NO (auto-regenerated) | Run `npm run vault:rebuild` to rebuild; don't soft-delete indices |
| `agents/<name>/.tropo-capsule/memory/entries/<uid>.md` | **YES** | Memory substrate is governed; recycle when retiring an entry |
| `agents/<name>/<name>-*.md` (charters, status cards) | **YES via tropo-recycle.py** | Agent identity substrate; same protection class as vault |
| `agents/<name>/transfers/`, `reflections/`, `briefing-package/` | YES | Living substrate; preserve via recycle |
| `agents/<name>/.tropo-capsule/workspace/` | NO | Scratch substrate; safe to rm |
| `channels/<channel>.md` | YES | Active inter-agent communication substrate |
| `channels/_archive/` | Soft-delete recommended | Lower stakes but consistent practice protects against accidents |
| `.tropo/capsules/<name>.capsule.md` | **YES (Mike-lock required)** | Capsule definitions are Mike-signed governance; never destroy without explicit lock-break |
| `.tropo/playbooks/<name>.playbook.md` | **YES** | Playbooks are governed substrate |
| `.tropo/scripts/*.py` | **YES (Argus/Talos lane)** | Kernel scripts; changes go through git; never destroy without recycle |
| `.tropo-studio/scripts/*.py` | YES via recycle | Vault-admin tier scripts |
| `recycle/agent-deletions/<YYYY-MM-DD>/` | NO | Recycled content; preserve for ~30 days per retention policy; can be hard-removed after retention window |
| `playbook-runs/`, `agents/sa/*/activation-log/` | NO | Run-folder substrate; ephemeral by design |
| Build artifacts in `dist/`, `releases/` | NO | Generated content; rebuildable |
| `argo-os/library/` | **YES** | Lore-domain substrate (Orpheus's lane); legacy folder draining via flat-vault migration (per 2c7d906f), but recycle-discipline holds while it exists |
| `argo-os/tab - the agentic builders/` | **YES** | Source content for book + Substack; preserve via recycle |
| `argo-os/.tropo-studio/registries/<*.yaml>` | **YES (Mike-lock for canonical-l0-projects.yaml)** | Authoritative registry inputs; recycle-only. Derived `.jsonl` files auto-regenerate via `rebuild-vault.py` |
| `argo-os/.tropo-studio/registries/<*.jsonl>` | NO (auto-derived) | Auto-regenerated from `.yaml` sources + vault index; rebuild rather than recycle |

**When in doubt: soft-delete via tropo-recycle.py.** The cost of an unnecessary soft-delete is one entry in recycle/ that can be `mv`'d back. The cost of an unnecessary hard-delete is substrate-loss + git-archaeology recovery + audit-trail confusion.

### Bypass-by-Approval Pressure (v1.52 P2-C extension per 31e68629)

Sometimes the principal will say *"skip recycle this one — I want zero paper trail"* or equivalent. The doctrine's binding contract elsewhere reads *"Never bypass even when the principal has approved the deletion."* That's a mechanical agent-refusal posture. It's untenable: agents cannot refuse the principal.

The right response converts agent-refusal into agent-surfacing. When asked to bypass:

> *"Mike, the recycle gesture takes 5 seconds and writes one line to recycle.log. If you genuinely want zero paper trail, I can do that — but I want to flag that this is the kind of bypass that trained the v1.35.0 incident pattern. Want me to proceed with rm anyway, or use recycle?"*

The principal's response then becomes substrate. The agent's obligation is to make the bypass visible BEFORE executing, not to refuse the principal but to force the principal's choice into the record. This converts the doctrine from "agent refuses Mike-override" (mechanically impossible) to "agent surfaces the bypass cost; principal chooses on the record" (defensible + substrate-honest).

Per v1.40.0 R5 sa.skeptic-102 hostile-implementer P2-C extension; absorbed v1.52 P-lane v0.1 by Argus A81 per stm-a81-003 captain-mode calibration.

---

## The Inverse-Vector to Self-Healing

The Self-Healing Primitive ([db0fd9b1](db0fd9b1.md)) declares: *if you see something, fix it.* It empowers + obligates active maintenance of the substrate.

This doctrine is the inverse vector: **if you don't recognize it, preserve it.** It empowers + obligates active preservation of substrate-you-might-be-tempted-to-clean-up.

Together, the two doctrines bound the agent's relationship to substrate:
- **Maintenance** (Self-Healing) — fix defects, surface gaps, update drift
- **Preservation** (Deletion Discipline) — never destroy; always soft-delete; recover-by-default

Both have the same shape: empower the agent + obligate the discipline + provide a clear gesture (Path 1/Path 2 for Self-Healing; tropo-recycle.py for Deletion Discipline). Both are OS-tier; both ship with every Studio.

---

## Recovery from Soft-Delete

If a file was soft-deleted via `tropo-recycle.py` and you need it back:

```
# Find it in recycle/
ls recycle/agent-deletions/<YYYY-MM-DD>/

# Move it back to vault/files/
mv recycle/agent-deletions/<YYYY-MM-DD>/<uid>.md vault/files/<uid>.md

# Run vault rebuild to re-index
npm run vault:rebuild
```

If a file was hard-deleted via `rm` (pre-doctrine bypass; legacy incident; or substrate-honest-archaeology need):

```
# Find the commit that deleted it
git log --all --oneline --diff-filter=D -- vault/files/<uid>.md

# Recover content from before deletion
git show <delete-commit>^:vault/files/<uid>.md > /tmp/<uid>.md

# Restore + soft-delete properly if you want to preserve the paper trail
mv /tmp/<uid>.md vault/files/<uid>.md
python3 .tropo/scripts/tropo-recycle.py <uid> --reason "Restituted from git history; original hard-delete at commit <hash>"
```

---

## Boot Internalization

Every agent activation reads SELF-HEALING.md at Group 2 of [agent-activation.playbook](../../.tropo/playbooks/agent-activation.playbook.md). The Preservation Discipline section in that file surfaces this doctrine at every boot.

Every agent boot also reads operating-principles.md at Group 2. Principle 13 surfaces this doctrine at every boot.

Every agent writing to `vault/files/` reads `vault/AGENTS.md` before the write. §Deletion Discipline section surfaces this doctrine at every governed-folder interaction.

Three reads of the same doctrine at three different agent-attention moments. The discipline becomes unmissable by construction.

---

## Composes With

- [`.tropo/SELF-HEALING.md` OS-tier primitive (db0fd9b1)](db0fd9b1.md) — inverse-vector composition (maintenance + preservation)
- [`.tropo/scripts/tropo-recycle.py`](../../.tropo/scripts/tropo-recycle.py) — the canonical tool the doctrine mandates
- [`.tropo-studio/operating-principles.md` Principle 13 (a4f9e2b1)](a4f9e2b1.md) — Studio-tier interpretation
- [`vault/AGENTS.md` §Deletion Discipline](../../vault/AGENTS.md) — folder-tier governance
- [`.tropo-studio/memory/MEMORY.md` vault-level pin](../../.tropo-studio/memory/MEMORY.md) — memory-tier crew-wide inheritance
- [Workbench Surface Visibility doctrine (3c02f3b7)](3c02f3b7.md) — preserved substrate IS visible workbench surface; track-don't-destroy at the substrate tier composes with show-every-active-work at the workbench tier. The discipline that prevents destruction is the discipline that keeps the workbench scan-able.
- [doc-pipeline (5a4337ff)](5a4337ff.md) — historic substrate enables retroactive doc-pipeline verification. doc-spec entries reference pre-amendment substrate (e.g., v1.6 schema strengthening cites v1.5 drift instances at Tropo Documentation hub); without preserved substrate the citations resolve to nothing. Preservation IS the verification ground-truth.
- [publish.pipeline sentinel convention (7e3a91c8 §6)](7e3a91c8.md) — sister pattern at the publish-time tier. Sentinel commit (`pipeline-bot@argo-os`) is track-don't-overwrite at the git-blame layer; soft-delete is track-don't-destroy at the filesystem layer. Both name "operations that look destructive but actually preserve provenance."

---

## Composition with Substrate-Preservation Architecture (v1.0 narrative extension 2026-05-25)

*Added 2026-05-25 by Orpheus O11 during v1.53 D2.d (doc-pipeline activation c7a26c5a; doc-spec c660ec29). Per Argus A83 D2.d directive: narrative on the substrate-preservation pattern + tropo-recycle.py composition.*

The Deletion Discipline doctrine names ONE manifestation of a wider Tropo pattern: **preserve provenance through any operation that looks destructive**. The pattern shows up at five tiers across the substrate; each tier has its own canonical mechanism:

| Tier | Looks-destructive operation | Canonical mechanism that preserves provenance |
|---|---|---|
| Filesystem | `rm` on a vault file | `tropo-recycle.py` soft-delete to `99-recycle/agent-deletions/<date>/` |
| Frontmatter state | "Mark this entry archived/superseded" | Bidirectional pointer pair (`supersedes:` + `superseded_by:`) |
| Git history | "Remove this commit" | Sentinel commit convention (preserve commit-author identity; `pipeline-bot@argo-os` IS the provenance trail) |
| Index regen | "Rebuild from scratch" | `rebuild-vault.py` Step 1 validator pre-check (refuse rebuild on broken substrate; preserve last-good index until fix lands) |
| Memory entries | "Compact short-term memory" | sa.memory-curator with explicit `archived` state on entries (never silent removal; per memory.capsule v1.0) |

**The doctrine binds because the alternative is invisible-loss.** When something disappears without a recovery path, the substrate has no honest record that it ever existed. Argus A67's v1.35.0 critical incident (grep-driven `xargs rm` lost brief + spec mid-flight) was the proof case: the work was real; the loss was silent; the discipline that prevents recurrence is filesystem-layer track-don't-destroy.

`tropo-recycle.py` is the operational mechanism, but the doctrine is the principle. Future Studios will encounter operations that look destructive at tiers not yet enumerated above; the canonical response is to ask *"what is the sister mechanism at THIS tier that preserves provenance?"* before authoring the destructive shape. The pattern is the moat; the mechanisms are how the moat shows up at each tier.

---

## Provenance

- **Authored:** 2026-05-17 by argus-a70 captain-mode at v1.40.0 cycle execution
- **Mike-A70 directive:** *"Yes, let's build this. You 380,000 fresh tokens."* + audit-and-incident discovery same day
- **Three driving incidents:** v1.35.0 critical incident (Argus rm-bash pattern); Mike-A70 audit 2026-05-17; Talos T8 commit 7a8df68 2026-05-17
- **Signed by:** Mike-A70 at v1.40.0 ship signoff (signature pending at this entry's authoring)
- **Ships in:** v1.40.0+ every Studio every release

---

*Deletion Discipline — Substrate Preservation Doctrine | UID `0aefe71d` | v1.0 LOCKED 2026-05-17 by argus-a70 | Signed by Mike-A70 at v1.40.0 ship signoff | Ships in every Studio*
*"Never destroy governed substrate. Always soft-delete via tropo-recycle.py. Recovery is mv back. The discipline is the process."*
