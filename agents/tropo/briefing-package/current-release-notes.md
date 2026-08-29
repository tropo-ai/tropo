---
uid: f6a967fd
type: release
agent: tropo
title: Tropo Release Notes — v1.93.0
description: Current Tropo release notes for delivery via Tropo's release-liaison role. Refreshed each release by the update pipeline. v1.93.0 makes the release runner actually drive a release — the deterministic steps are machine-executed, and the walk halts only where a human must judge or a precondition is unmet, naming a runnable command at every stop. It ships one capability by deliberate scope, because this release exists to answer one measurable question — did releasing get cheaper — and a larger release would confound the answer. Behind that, a step whose executor fails after starting can now be returned to runnable with its cause journaled instead of stranding the run, and the release history a build writes is no longer silently skipped when part of it was already there.
release_version: v1.93.0
release_date: '2026-08-28'
last_delivered_version: null
audience: Studio user (whoever opened this Studio)
read_first_at: Group 2 boot (release-state awareness check)
delivered_at: Pattern 1 returning user OR Pattern 3 scheduled summary; suppressed if last_delivered_version matches
created: '2026-05-10'
created_by: argus-a55
modified: '2026-08-28'
modified_by: argus-a160
schema_version: 2
extraction_scope: ship
governance_class: kernel-managed
governed_by: 222873b9
member_of:
  - 03ccd072
tags:
  - tropo-release-notes
  - v1.91.0
  - kernel-managed
  - release-liaison-content
  - refreshed-each-release
subsystem_hub:
  - 99ed55fd
  - 8dd772a0
retyped_from: release-notes
retyped_at: '2026-07-12'
retyped_by: argus-a130 (walked disposition 5dcbadbd, Mike-verdicted, S2 activation 0d9f89bc)
---

# Tropo v1.93.0 — Release Notes

*The current Tropo release. Delivered by Tropo's release-liaison role at Pattern 1 returning user startup OR Pattern 3 scheduled summary.*

**Headline: the build that does not need a human hand.**

- **The build runs start to finish with no bypass flag.** The record defects that forced an
  enforcement override on every v1.90 build are cured at the record, and any bypass that ever
  survives is written into build provenance — a skipped gate can no longer be silent.
- **Every declared release event has exactly one writer.** Four events that had readers, refusal
  messages and tests but no emitter (including the release's own human-authorization records) now
  reach the bus from the point where their fact is recorded; a declared event with no writer fails
  at validate, not at your first recovery.
- **Everything that can refuse refuses before you say yes.** One preflight runs every fire
  precondition — credentials probed read-only, CHANGELOG checked at build, the website badge written
  by an adapter to the repository the site actually deploys from — so a confirmed fire cannot stall
  on a precondition afterward.
- **The instruments were verified as a stranger would use them.** Every acceptance criterion behind
  this release was run on its locked command, byte for byte, by someone other than its author; five
  verification commands that were blind or absent were found that way and fixed inside the cycle.
- **Validator answers arrived enumerable and fast.** The failure count now equals the printed
  findings (no invisible debt), one debt predicate answers the debt question everywhere, and the
  strict membership check dropped from twelve minutes to half a minute.

*Refreshed 2026-08-23 for v1.91.0 by metis-g111 at build (G111 driving; verification ledger at boards/_data/v191-verification.jsonl).*
