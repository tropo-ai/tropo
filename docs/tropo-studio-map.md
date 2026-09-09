---
uid: '3e581123'
type: kb-article
title: "The Studio Map"
description: "The router: one concise surface that orients any booting agent (and any human) to the Studio's capabilities, tools, skills, rules, and locations. It points, it never restates. One of the Studio's two canonical documents, beside the Architecture Review."
status: published
state: active
owner: metis
author: metis-g113
member_of:
  - "8dd772a0"
created: '2026-08-27'
created_by: metis-g113
modified: '2026-09-09'
modified_by: metis-g127   # the four Architecture Review links repointed v4 → v5 (v4 stopped shipping, Mike-ruled 2026-09-09); rows not re-verified, as_of unchanged
as_of: '2026-09-05'   # the date every hand-written row below was last verified against the tree; the render prints it (v1.95 A5 accuracy plan)
as_of_release: '1.95.0'
schema_version: 2
governed_by: 8dd772a0
extraction_scope: ship
proposer: mike-maziarz
refs:
  - fc316d7f
  - b955b2b8
  - 266b0b56
  - a993f079
tags:
  - studio-map
  - orientation
  - router
  - canonical-document
---

# The Studio Map

*The router. One page that tells you where everything is and when to reach for it. It points and
never restates — the law lives where the links go, and restating is how maps rot. Sibling canon:
[the Architecture Review](architecture-review-v5/tropo-l1-architecture-review.md) (WHAT the system
is and why — read-at-need for architecture work) and, for crew shorthand, the Studio Dictionary
(`b955b2b8`, in design). This Map and the Review are the Studio's **two canonical documents**
(Mike-ruled 2026-08-26), refreshed every release or two by the Metis line at Mike's commission.*

---

## 1 · Where you are

**Tropo** is the operating system (Greek τρόπος, "way"). A **Studio** is one installation — this
folder. The **Vault** (`vault/`) is the governed content store inside it. The thesis in one line:
as execution cost falls, the binding constraint is human verification bandwidth — so the process
is machine-guaranteed and the human verifies results at defined gates. Full statement:
[mission brief](../.tropo-studio/mission-brief.md). Identity and invariants:
[TROPO-CONTROL](../.tropo/TROPO-CONTROL.md) · [STUDIO.md](../STUDIO.md).

## 2 · The moment index — when to reach for what

*The block that changes behavior. One line per working moment; the link is the depth.*

| You are about to… | Reach for |
|---|---|
| Boot | The mechanism, not this Map: [fast-path](../.tropo/boot-fast-path.md) + [digest](../.tropo/boot-digest.md). First generation: the [canonical playbook](../vault/playbooks/99341618.md) |
| Scope, design, or rule on a governed domain | `python3 vault/tools/tropo-orient.py --task <uid> --as <you>` — read the whole neighbourhood; an honest empty answer is a feed-gap finding to file, never a reason to skip |
| Send substantive work to Mike | Dispatch an adversarial reviewer first ([commission-quickref](../agents/sa/commission-quickref.md)); never co-sign a subagent report you did not verify first-hand |
| Verify another agent's claim | Run its locked command **verbatim**, as a non-author; receipts, not reading |
| Build something new | Scan first: governing briefs/specs in the index, existing implementations in the code, the type's [capsule](../vault/capsules/) — capsules have the truth; a divergence is a finding |
| Use a capability | The catalogs: [tools](../.tropo/tool-catalog.md) · [skills](../.tropo/skill-catalog.md) · [session agents](../.tropo/sa-agent-catalog.md) · [toolbelt](../.tropo/toolbelt.md). The rule: if it exists, use it |
| Find anything | `python3 vault/tools/tropo-vault-search.py "<query>"` (add `--include-archive` for history) · SQLite edges+FTS at `vault/00-index.sqlite` · project tree `vault/00-project-tree.jsonl` |
| Create a governed file | `python3 vault/tools/tropo-mint-id.py` for the uid · the folder's CAPSULE for the rules · `tropo-rebuild-index.py --only <uid>` to register |
| Delete anything governed | `python3 vault/tools/tropo-recycle.py <uid> --reason "…"` — never `rm` |
| Message another agent | `tropo-emit-event.py` at their **party UID** — and land the assignment on the governing record in the same gesture; an agent's queue is built from records, not messages |
| Collaborate live this session | Arm an origin watch per the [wake discipline](../.tropo/WAKE-DISCIPLINE.md): fetch before you listen; a wake is never authority |
| Resume after compaction | `python3 vault/tools/tropo-compact-continue.py --agent <slug>` — never `born` |
| Retire | Only when Mike signals. [The playbook](../vault/playbooks/e2c7d185.md), all eight steps; the driver verifies them on the world |
| Act on a defect you noticed | [Self-Healing](../.tropo/SELF-HEALING.md): trivial → fix in place; substantive → file in the relevant inbox; never read past it |
| Keep a learning | Tropo memory, never the harness store: append to your `agent-memories.jsonl` in-session; crew-class goes to [studio memory](../.tropo-studio/memory/memory-current.md) |
| Render for Mike | `boards/<agent>/`, readable names first, links clickable; questions in the [walk format](../.tropo-studio/memory/entries/54f514e8.md), one per turn, your lean stated |
| Add a gate, check, or process | Answer first: what is the irreversible harm, in one sentence, and what does Mike lose without it? Warn-safe is the default (`deb77758`); the default is cut |
| Ship | [How We Build Software](how-we-build-software.html) — the process canon: two locks and a fire; then [RELEASING.md](../vault/templates/root-docs/RELEASING.md), the release procedure as it ships |
| Change any output format | Ask "who else reads this?" and visit every reader — the studio's costliest defect family is one fact, two readers, one updated |
| Get lost | This Map §5, then the [Architecture Review](architecture-review-v5/tropo-l1-architecture-review.md) |

## 3 · The rules that bind

One line each; the link is the law. [The 15 Operating Principles](../.tropo-studio/operating-principles.md)
(read the [digest](../.tropo/boot-digest.md) at boot; the full file when a rule is in play) ·
[Self-Healing](../.tropo/SELF-HEALING.md) (P0: see it, act now) ·
[Wake Discipline](../.tropo/WAKE-DISCIPLINE.md) (fetch before you listen) ·
[Human Navigation](../.tropo/HUMAN-NAVIGATION.md) (the rendered surface is a deliverable) ·
[Canonical Taxonomy](../.tropo-studio/CAPSULE.md) (Tropo · Studio · Vault; fix old vocabulary on
encounter) · [Deletion Discipline](../vault/files/0aefe71d.md) (soft-delete only) ·
warn-safe default ([deb77758](../.tropo-studio/memory/entries/deb77758.md)) · before architectural
calls, verify against canon: [STUDIO.md](../STUDIO.md), the
[L0 registry](../.tropo-studio/registries/canonical-l0-projects.yaml), the type's capsule (OP-11).

## 4 · The capability surfaces

All **generated from the index** — read them, never edit them:
[toolbelt](../.tropo/toolbelt.md) (the core belt) · [tool catalog](../.tropo/tool-catalog.md) ·
[skill catalog](../.tropo/skill-catalog.md) · [session-agent catalog](../.tropo/sa-agent-catalog.md).
Playbooks live at [vault/playbooks/](../vault/playbooks/); actions at
[vault/actions/](../vault/actions/); loops are `type: loop` entries in the index. Before spawning
any sa.*: [commission-quickref](../agents/sa/commission-quickref.md).

## 5 · The location contract — what lives where, and what may not

| Location | Holds | May never hold |
|---|---|---|
| `.tropo/` | The kernel: the cold-boot floor (thin pointers with degraded floors), the boot digests, generated catalogs, machine flags | Full-bodied reference content; anything with a vault canonical |
| `.tropo-studio/` | This install's config and institutional memory: operating principles, mission, registries, studio memory | Work items; per-agent substrate |
| `vault/` | The governed store: every typed artifact at `files/<uid>.md`, One-Home type dirs (capsules, tools, skills, playbooks, actions, session-agents, agents), the event ledger, run journals | Ungoverned scratch; standalone reference folders |
| `agents/` | Per-agent homes (activation pointer, capsule, memory, transfers, lineage) + sa.* records | Crew-shared doctrine (that is the vault's or this folder's job) |
| `docs/` | **The two canonical documents** — this Map and the Architecture Review — plus the process canon and their assets | Anything else, without Mike's word (see this folder's CAPSULE) |
| `boards/` | Rendered surfaces for humans | Canonical content (renders are snapshots; regenerate) |
| `playbook-runs/`, `vault/pipeline-runs/`, `vault/loop-runs/` | Machine journals, append-only | Hand edits (seed contracts apply; rulings live in canonical homes) |
| `tropo-app/` | The L2 cockpit (Next.js) — a window onto Tropo Work, never the store | State that belongs in the vault |
| `../tropo-releases/`, the sibling folder beside the studio | Built release artifacts, one folder per version (`tropo_roots.RELEASES_DIR`) | Anything an agent edits |

## 6 · Where the work is

Current cycle and crew: [00-crew-brief](../00-crew-brief.md) (auto-rendered from lineage) ·
boards at `boards/` · a project's `01-inbox`, where it keeps one, walks up to the
[studio inbox](../vault/files/2d5f9b04.md) · pipelines and runs in the index
(`type: pipeline`, `type: pipeline-run`) · the release process:
[How We Build Software](how-we-build-software.html).

## 7 · Reading order

**At boot:** the fast-path and digest are the mechanism; this Map is a full read (Mike-ruled
2026-08-30 — was a §2-only skim; see boot-fast-path Step 3a).
**At need:** everything §2–§6 points to, one hop away.
**For depth:** [the Architecture Review](architecture-review-v5/tropo-l1-architecture-review.md)
— what the system is, why it is shaped this way, and its honest failure record, re-verified
against the live substrate on its own dated schedule.

---

*The Studio Map | uid `3e581123` | one of the two canonical documents (with the
[Architecture Review](architecture-review-v5/tropo-l1-architecture-review.md), Mike-ruled
2026-08-26) | refreshed every release or two, Metis-line, Mike-commissioned | it points, it never
restates | fingerprint-gated into the boot digest so drift fails loud | replaces the retired
kernel index and the hand-maintained sa.* indexes (2026-08-27 consolidation).*
