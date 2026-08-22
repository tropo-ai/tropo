---
uid: f6a967fd
type: release
agent: tropo
title: Tropo Release Notes — v1.90.0
description: Current Tropo release notes for delivery via Tropo's release-liaison role. Refreshed each release by the update pipeline. v1.90.0 makes the update itself trustworthy: every outward act of a release is journalled and resumable, the site push is a compare-and-swap that refuses instead of overwriting, the update feed resolves every URL it names before a release is called live, and updating a studio is lift-and-replace — planned against a manifest, applied over a backup, with the old machinery retired rather than layered.
release_version: v1.90.0
release_date: '2026-08-22'
last_delivered_version: null
audience: Studio user (whoever opened this Studio)
read_first_at: Group 2 boot (release-state awareness check)
delivered_at: Pattern 1 returning user OR Pattern 3 scheduled summary; suppressed if last_delivered_version matches
created: '2026-05-10'
created_by: argus-a55
modified: '2026-08-21'
modified_by: talos-t48
schema_version: 2
extraction_scope: ship
governance_class: kernel-managed
governed_by: 222873b9
member_of:
  - 03ccd072
tags:
  - tropo-release-notes
  - v1.90.0
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

# Tropo v1.90.0 — Release Notes

*The current Tropo release. Delivered by Tropo's release-liaison role at Pattern 1 returning user startup OR Pattern 3 scheduled summary.*

**Headline: updates that cannot lie, and a release you can pause mid-stride.**

- **Every outward act of a release is now a journalled step.** A fire that dies halfway is describable and resumable by checkpoint — the journal says what happened, and the release refuses to claim success for any act it cannot show.
- **The one push is a compare-and-swap.** If the remote moved, the release refuses and says so — it never overwrites a counterpart's commit, including under deadline pressure.
- **The update feed tells the truth.** A release is not called live until every URL its manifest names actually resolves — the failure that shipped two releases with no update package is now structurally impossible.
- **Updating a studio is lift-and-replace.** A plan computed against the image's manifest, an apply over an automatic backup with a receipt, and a migration contract that refuses undeclared passengers. A legacy studio self-heals to full mode after its first lift. Measured end to end, the lift runs in seconds.
- **The old machinery is retired, not layered:** the fragile delta tool, the hand-walked apply playbook, and the migrate step that could rewrite user content are gone.

*Refreshed 2026-08-21 for v1.90.0 by talos-t48 at ignition (G109 driving, A153 verify on record).*
