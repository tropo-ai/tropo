---
uid: 61f650aa
type: capsule-definition
name: numeric-folder-prefix
version: "1.0"
title: "Numeric Folder Prefix — Two-Axis OS-Tier Folder Naming Doctrine"
description: "Tropo-OS canonical doctrine governing numeric-prefix folder naming across every Studio. Two axes: AXIS 1 numeric ordering (00-09 reserved Tropo-OS workflow-positioned conventions; 10+ available for studio-specific scoped category folders); AXIS 2 terminal positioning (99- as always-last folder-local convention, independent of axis 1). Walked verbatim by Mike-G58 + Metis G58 2026-05-23 during the publish.pipeline design-stage brainstorm; filed as Path 2 finding [7e4c2b81] for Argus canonical capture; LOCKED v1.0 by Argus A81 2026-05-24 captain-mode per Mike-A81 strong-lean calibration (stm-a81-003) as v1.52 P-lane P3 deliverable."
status: locked
state: active
author: argus-a81
created: 2026-05-24
modified: 2026-05-25
created_by: argus-a81
modified_by: orpheus-o11
v1_0_narrative_extension_note: "v1.0 narrative extension 2026-05-25 by orpheus-o11 during v1.53 D2.c (doc-pipeline activation c7a26c5a; doc-spec c660ec29). Added Workbench Surface Visibility doctrine (3c02f3b7) row to §8 Composability table per Argus A83 D2.c directive: cross-tier integration narrative naming the binding composition between folder-prefix mechanism (this capsule) + workbench-visibility principle (the doctrine). Schema unchanged; narrative-only amendment per §9 Amendment Protocol cosmetic-clarification class (no version bump)."
locked_at: 2026-05-24
locked_by: argus-a81
walk_locked_at: 2026-05-24
walk_walked_by: [mike-g58, metis-g58]
walk_locked_by: mike-g58
schema_version: 2
extraction_scope: ship
governed_by: 8dd772a0   # tropo-governance
member_of:
  - "8dd772a0"   # tropo-governance subsystem
composes_with:
  - "7e4c2b81"   # Path 2 finding — source doctrine (Metis G58 + Mike-G58 walk)
  - "9d3a6f17"   # AGENTS.md governance contracts finding (P4 — composes here)
  - "2f5e8c1a"   # publish.pipeline Package Step Refinements (uses 02-outbox + 03-design naming)
  - "5b3e9c47"   # publish.pipeline Design Step Spec (uses 02-outbox + 03-design naming)
  - "a5f4b26b"   # Captain's Briefing v3.0 (asymmetric I/O design principle this materializes — outbox is the export surface)
  - "eca73d77"   # L1 canonical entry (Canonical Taxonomy lives here; cross-references this doctrine)
  - "404ac636"   # v1.52 cycle brief (P3 deliverable absorbs this doctrine canonically)
  - "f8bf8c4a"   # v1.52 dev-spec (committed_substrate P3 entry)
tags: [capsule-definition, os-tier-doctrine, folder-naming-convention, numeric-prefix, two-axis, tropo-system-reservation, studio-specific-pattern, terminal-positioning, governance, locked-2026-05-24, v1-52-p-lane-p3]
applies_to: "Every Studio (Tropo-OS canonical doctrine; not studio-specific overridable)"
ratchet_schedule: "v1.0 Validation Checks at WARN-severity; v1.1 ratchet to ERROR after evidence of clean operational use across ≥ 2 cycles + ≥ 1 fresh Studio install"
---

# Numeric Folder Prefix — Two-Axis OS-Tier Folder Naming Doctrine

<!-- nav-block:start -->
**🔗 This file** — UID `61f650aa` · type `capsule-definition` · state `active` · status `locked`
<!-- nav-block:end -->

*OS-tier canonical doctrine governing how numeric-prefixed folders are named across every Studio. Walked verbatim by Mike-G58 + Metis G58 2026-05-23 during the publish.pipeline design-stage brainstorm; filed as Path 2 finding [7e4c2b81](../../vault/files/7e4c2b81.md) for Argus canonical capture; LOCKED v1.0 here as v1.52 P-lane P3 deliverable.*

*Two axes: numeric ordering on axis 1, terminal positioning on axis 2. No overload between them.*

---

## 1. Intent

Numeric-prefixed folder names (e.g., `01-inbox/`, `02-outbox/`, `99-archive/`) are governed by this doctrine across every Tropo Studio. The prefix signals **systematized purpose** — a folder named `02-outbox/` carries the same convention semantics in every Studio. Studios cannot rename `02-outbox/` to `outgoing/` and still claim Tropo-conformance; the convention IS the prefix.

Three things this doctrine fixes:

- **Cross-Studio portability** of conventions: every Studio that opens a vault sees `01-inbox/` and knows the contract without reading the AGENTS.md
- **Reserved-namespace discipline**: tropo-system conventions (00-09) cannot be claimed by studio-specific work; studio-specific conventions (10+) cannot collide with tropo-system reservations
- **Terminal-positioning honesty**: `99-` folders sort last in every listing and communicate "end" semantically without overloading the axis-1 ordering

This is OS-tier governance because the doctrine governs naming across every Studio (not just Argo), and a Studio that breaks the convention loses portability across the Tropo ecosystem.

---

## 2. The Two-Axis Rule

### AXIS 1 — Numeric ordering for workflow-positioned conventions

| Prefix range | Reservation | Rule |
|---|---|---|
| **00-09** | **Tropo-OS reserved** | Studios cannot claim these numbers. Conventions in this range are tropo-system canonical and apply uniformly across every Studio. |
| **10+** | **Available for studio-specific scoped category folders** | Each Studio defines its own conventions starting at 10. Studio-specific 10+ folders require a governance contract (AGENTS.md at folder root) per Validation Check 4 below. |

**The prefix signals systematized purpose.** Reading any numeric-prefixed folder tells an agent immediately: this folder is governed; check AGENTS.md and the canonical contract (this capsule or studio-specific equivalent) for the rules.

### AXIS 2 — Terminal positioning (independent of axis 1)

| Prefix | Convention | Rule |
|---|---|---|
| **99-** | **ALWAYS-LAST folder-local terminal** | Sorts at the bottom of any folder listing. Communicates "end" or "terminal disposition" semantically. Applies independent of axis 1 (any scope can use 99- for terminal stuff). |

**Why two axes, not one.** Putting `archive` at `09-archive` would overload `09`'s meaning (it would mean "the last numbered tropo-system slot," not "terminal disposition"). Putting it at `99-archive` keeps the slot semantics distinct: `09` stays a numeric-ordered tropo-system slot reserved for future workflow-positioned conventions; `99` is the terminal-positioning axis. Two axes, no overload.

---

## 3. Active 00-09 Tropo-OS Reservations

| Prefix | Convention | Scope | Purpose |
|---|---|---|---|
| `00-` | index / navigation | any scope | Index + navigation artifacts. Examples: `00-index.md`, `00-project-tree.jsonl`, `00-cascade-*.jsonl`, `00-tropo-nav/`. |
| `01-inbox` | lifecycle: incoming work | per-project | Items entering a project's work pipeline. Canonical at every governed project. Examples: `vault/files/0a1a36fe.md` (dev-pipeline 01-inbox), per-project 01-inbox folders. |
| `02-outbox` | lifecycle: outgoing publications | studio-root | The going-out-to-the-world surface. Receives publish.pipeline outputs; mirrors site/medium/section structure. Canonical example: `argo-os/02-outbox/` (renamed from `external-work/` 2026-05-23). |
| `03-design` | design substrate | multi-scope | Brand kit + design assets. Format adopts Claude Design export (DTCG-aligned industry-portable). Composes via filesystem hierarchy across studio-root and lower scopes (per [5b3e9c47](../../vault/files/5b3e9c47.md) §Brand-Kit Inheritance). Canonical example: `argo-os/03-design/`. |
| `04-09` | RESERVED FUTURE | — | Reserved for future tropo-system workflow-positioned conventions. Studios cannot claim these. |

**Authority:** Adding a new 00-09 reservation requires Mike-walked + Argus-authored amendment to this capsule. v1.1 amendment shape: append row to table + amend §3 + bump version.

---

## 4. Active 99- Terminal Conventions

| Pattern | Scope | Purpose | Canonical example |
|---|---|---|---|
| `99-archive/` | folder-local | Where THIS folder's retired/completed items live. Any project or governed folder can have its own 99-archive/. | `argo-os/.tropo/capsules/99-archive/` (pre-existing canonical instance) |
| `99-recycle/` | studio-root | The Studio's soft-delete bin. Target of `tropo-recycle.py`. One per Studio. | `argo-os/99-recycle/` (renamed from `argo-os/recycle/` 2026-05-23) |

**99-archive vs 99-recycle distinction:** 99-archive holds retired-but-preserved substrate (honest historical record per [vault/.tropo-studio/CAPSULE.md](../../vault/.tropo-studio/CAPSULE.md) deletion-discipline). 99-recycle holds soft-deleted substrate awaiting hard-delete or recovery; tropo-recycle.py is the canonical mover.

---

## 5. Studio-Specific 10+ Pattern (Governance Contract)

Studios MAY define their own numeric-prefixed folders starting at `10`. Each studio-specific 10+ folder requires governance:

| Requirement | Form | Rationale |
|---|---|---|
| **AGENTS.md at folder root** | Markdown file at `<studio-root>/<NN-name>/AGENTS.md` | Documents who can write, what belongs, and what protocols apply (per [9d3a6f17](../../vault/files/9d3a6f17.md) P4 finding governance pattern) |
| **Canonical contract reference** | AGENTS.md frontmatter declares `canonical_contract:` field referencing this capsule UID `61f650aa` | Provides the OS-tier convention link a stranger-engineer can trace |
| **Numeric stability** | Once allocated, a 10+ prefix cannot be renumbered without amendment cascade through all references | Prevents prefix-churn breaking external references |
| **Folder rename to `10+`** | If a Studio retroactively conforms (e.g., renames `library/` → `15-library/`), the AGENTS.md authoring is the lock-event | Conforms the folder to this convention's governance |

**No 10+ at vault-root.** Vault subfolders follow the `vault/files/` flat-vault discipline (per Mike's binding pin `feedback_flat_vault_doctrine`). Numeric-prefix folders sit at studio-root or sub-project root, not under `vault/`.

---

## 6. Validation Checks

Per `tropo-validate.py` extension at v1.52 (WARN at v1.0; ERROR ratchet at v1.1 per ratchet_schedule):

### Check 1 — `check_numeric_folder_prefix_reserved_range`

**Severity:** WARN at v1.0; ERROR at v1.1.

**Scans:** every numeric-prefixed folder under `<studio-root>/` matching pattern `^\d{2}-`.

**Asserts:** if prefix is in `[00, 01, 02, 03, 04, 05, 06, 07, 08, 09]`, the folder name matches a row in §3 (active tropo-system reservations). If `04-09` reserved-future range, only Mike-walked amendments to this capsule add new entries.

**Fails on:** studio-claimed folder at 00-09 not appearing in §3.

### Check 2 — `check_studio_specific_folder_has_agents_md`

**Severity:** WARN at v1.0; ERROR at v1.1.

**Scans:** every numeric-prefixed folder under `<studio-root>/` matching pattern `^[1-9]\d-` (i.e., 10+).

**Asserts:** AGENTS.md exists at folder root.

**Fails on:** 10+ folder without AGENTS.md governance contract.

### Check 3 — `check_99_terminal_convention`

**Severity:** WARN at v1.0; ERROR at v1.1.

**Scans:** every folder matching pattern `^99-`.

**Asserts:** folder name matches a §4 row (currently `99-archive/` folder-local OR `99-recycle/` studio-root).

**Fails on:** novel 99- folder name not in §4 (signals doctrine extension needed).

### Check 4 — `check_no_vault_subfolders_numeric_prefix`

**Severity:** WARN at v1.0; INFO at v1.1 (this is honest-record check; flat-vault doctrine binding).

**Scans:** every subfolder under `vault/` (excluding `vault/files/`).

**Asserts:** no numeric-prefixed folders directly under `vault/`. (Flat-vault discipline.)

**Fails on:** `vault/01-something/`, `vault/02-something/`, etc.

---

## 7. Worked Examples (the Studio as test instance)

The doctrine is operationally live at Argo as of 2026-05-23:

| Folder | Axis | Convention | State |
|---|---|---|---|
| `argo-os/00-tropo-nav/` | 1 (tropo-system 00) | index/navigation | live; pre-existing |
| `argo-os/01-inbox/` (per-project, multiple) | 1 (tropo-system 01) | lifecycle: incoming work | live at multiple project scopes |
| `argo-os/02-outbox/` | 1 (tropo-system 02) | lifecycle: outgoing publications | live; renamed from `external-work/` 2026-05-23 |
| `argo-os/03-design/` | 1 (tropo-system 03) | design substrate | live; created 2026-05-23 with Tropo brand kit v0.3 |
| `argo-os/.tropo/capsules/99-archive/` | 2 (terminal) | folder-local archive | live; pre-existing canonical instance |
| `argo-os/99-recycle/` | 2 (terminal) | studio-root soft-delete bin | live; renamed from `argo-os/recycle/` 2026-05-23 |

the Studio is fully conformant to v1.0 of this doctrine. New Studio installs inherit this conformance via the starter substrate.

---

## 8. Composability

This capsule composes with several substrate primitives:

| Composes with | How |
|---|---|
| [9d3a6f17 AGENTS.md governance contracts](../../vault/files/9d3a6f17.md) | P4 finding — AGENTS.md governance pattern is the implementation layer for §5 studio-specific 10+ rule + §4 99- conventions. P4 work in v1.52 authors AGENTS.md at `argo-os/02-outbox/` + `argo-os/03-design/` (the two new tropo-system folders this capsule formalizes) |
| [publish.pipeline.capsule](publish.pipeline.capsule.md) | Package step (`2f5e8c1a` v1.3) + design step (`5b3e9c47` v1.1) use `02-outbox/` + `03-design/` naming. Both compose with this capsule. v1.52 P-lane P1 + P2 amendments to publish.pipeline.capsule reference this capsule as the folder-naming canonical contract |
| [Canonical Taxonomy at L1 (eca73d77)](../../vault/files/eca73d77.md) | The Tropo/Studio/Vault canonical taxonomy is the parent convention; this capsule is a sibling doctrine about how the filesystem under Studio is named. L1 entry cites this capsule as the folder-naming canonical reference |
| [vault/.tropo-studio/CAPSULE.md](../../vault/.tropo-studio/CAPSULE.md) | The vault governance capsule references `99-recycle/` as the soft-delete target; this capsule formalizes the 99- terminal convention vault/.tropo-studio/CAPSULE.md cites operationally |
| Future studio-specific 10+ folder amendments | This capsule is the canonical contract every studio-specific 10+ AGENTS.md references via `canonical_contract: 61f650aa` |
| [Workbench Surface Visibility doctrine (3c02f3b7)](../../vault/files/3c02f3b7.md) | Folders are workbench surface; numeric prefix is the human-navigation contract that makes the workbench scan-able in 5 seconds. The prefix signals "where this folder lives in operator attention-order" — 00-inbox first; 02-outbox before 03-design; 99-archive last. Composition lock: folder-prefix discipline IS workbench-visibility discipline at the filesystem tier; the two doctrines compose at every Studio install (Workbench Surface Visibility names the principle; this capsule names the mechanism) |

---

## 9. Amendment Protocol

| Amendment class | Authority | Cascade |
|---|---|---|
| New 00-09 row (tropo-system reservation) | Mike-walked + Argus-authored | Updates §3 table + bump version (v1.x → v1.x+1) + cascade citations to other capsules using the convention |
| New 99- pattern | Mike-walked + Argus-authored | Updates §4 table + bump version + composability check on tropo-recycle.py + folder-local archive scripts |
| Validator check addition | Argus-authored | Adds row to §6 + wires into tropo-validate.py + ratchet_schedule entry |
| Studio-specific 10+ rules clarification | Argus-authored captain-mode | Updates §5 body + bumps version only if rule meaning changes (cosmetic clarifications can amend in-place without bump) |
| Ratchet WARN → ERROR | Argus-authored after ratchet_schedule criteria met | Updates ratchet_schedule frontmatter field + Validation Check severity columns + bump version |

---

## 10. Provenance

- **Doctrine source:** Mike-G58 + Metis G58 walk 2026-05-23 during publish.pipeline design-stage brainstorm. Three Mike-G58 verbatim quotes locked the doctrine (per [7e4c2b81](../../vault/files/7e4c2b81.md) §The doctrine Mike-G58 locked verbatim).
- **Filed:** Path 2 finding [7e4c2b81](../../vault/files/7e4c2b81.md) v0.2 by Metis G58 2026-05-23.
- **Routed:** to Argus A79's lane per Metis G58 routing note (Argus is OS-tier governance owner).
- **Canonical capture authority:** Argus A81 captain-mode 2026-05-24 per Mike-A81 strong-lean calibration (stm-a81-003) as v1.52 P-lane P3 deliverable.
- **Home choice:** new capsule (option 2 in [7e4c2b81](../../vault/files/7e4c2b81.md) §Probable canonical homes). Two-axis doctrine warrants typed-primitive treatment per Metis G58 lean + Argus A81 agreement. Composes with the existing `.tropo/capsules/*.capsule.md` pattern.
- **v1.52 cycle context:** P3 deliverable per cycle brief [404ac636 v0.2 LOCKED](../../vault/files/404ac636.md) §3 P-lane + dev-spec [f8bf8c4a](../../vault/files/f8bf8c4a.md) committed_substrate entry.

---

*Numeric Folder Prefix Capsule v1.0 LOCKED 2026-05-24 by Argus A81 captain-mode per Mike-A81 strong-lean doctrine. Tropo-OS canonical doctrine; binding across every Studio.*

*"Two axes: 00-09 tropo-system / 10+ studio-specific (numeric ordering); 99- always-last terminal (independent). The prefix signals systematized purpose; the number communicates the semantic."*
