---
uid: f6a967fd
type: release
agent: tropo
title: Tropo Release Notes — v1.96.0
description: Current Tropo release notes for delivery via Tropo's release-liaison role. Refreshed each release by the update pipeline. v1.96.0 is the first-two-days release. A stranger unzips a Studio, boots the concierge, mints a companion, retires it, and gets back to it tomorrow; each of those was measured on a built box by a cold reader and fixed where the box told a different story than the prose. The one machinery item is the promotion lane, one named command that ships the run it was told, bound to the bytes that were judged.
release_version: v1.96.0
release_date: '2026-09-09'
last_delivered_version: null
audience: Studio user (whoever opened this Studio)
read_first_at: Group 2 boot (release-state awareness check)
delivered_at: Pattern 1 returning user OR Pattern 3 scheduled summary; suppressed if last_delivered_version matches
created: '2026-05-10'
created_by: argus-a55
modified: '2026-09-09'
modified_by: metis-g127
schema_version: 2
extraction_scope: ship
governance_class: kernel-managed
governed_by: 222873b9
member_of:
  - 03ccd072
tags:
  - tropo-release-notes
  - v1.96.0
  - kernel-managed
  - release-liaison-content
  - refreshed-each-release
subsystem_hub:
  - 99ed55fd
---

# Tropo v1.96.0 — Release Notes

*The current Tropo release. Delivered by Tropo's release-liaison role at Pattern 1 returning user startup OR Pattern 3 scheduled summary.*

**Headline: the first-two-days release. Unzip, boot, meet Po, mint a companion, retire it, come back tomorrow — and find it there.**

- **Come back tomorrow works.** A companion's day-one learning, written through the shipped
  memory skill, is read at its day-two boot. The activation pointer minted for each companion
  carries the one line to type to reach the same agent again. This was walked on a built box by
  two separate sessions with no shared context, and the day-two session saw what day one wrote.
- **A first boot that says what it actually read.** Every agent's activation opens a read window
  and closes with a report of the files the harness observed it read, or an explicit "not
  observable in this harness" instead of an invented count. A read whose content matches inside
  the window counts as observed, with line coverage marked unknown where the harness gives none.
  Po's first message tells you what she can do, what she read, and how to come back tomorrow.
- **First setup is quiet.** The index build that runs the first time you open a Studio keeps its
  full output in a log, preserves its exit status, and shows you the real error only if it fails.
  You no longer read twelve hundred lines of diagnostics before the greeting.
- **`npm test` on a fresh Studio builds the index once, says so once, then answers honestly**
  instead of reporting failure on a perfect box that had not been initialized.
- **Retirement speaks to your principal, not ours.** The shipped retirement playbook named
  Tropo's founder as the customer's authority and required a crew brief no Studio of yours
  carries; a first retirement could never read complete. It now speaks to "your principal", the
  crew-brief step is not applicable in a Studio that keeps none, and the retirement driver says so
  instead of reporting an open step forever.
- **The promotion lane.** For the crew that builds Tropo, and for any Studio that cuts its own
  releases: `promote --version X.Y.Z --activation-uid <uid>` resolves the run it is told rather
  than the newest file on disk, runs the fire preflight once and the ship shadow once, prints both
  verdicts in full, and asks once. A publication that already completed is never re-fired silently
  and never denied outright: the guard warns, explains, and lets the founder decide. The zip is
  hashed against its receipt before upload.
- **The Architecture Review v5** ships as the one review in the box, fifteen self-contained
  figures and a diagram index the Studio Map renders from. v4 has left the box.
- **Cal and Darin are named** in the README and START-TROPO before Po offers them.
- **Identity first, then a first agent, in plain words.** Right after the greeting Po asks your
  name and the Studio's name and purpose, then suggests Darin first and Cal second in the founder's
  own language. Your founder record is minted complete, with a default accountability scope you can
  edit, so your first health check is not red on your own name. On a plain-files Studio, the two
  retirement steps that read the captain's log and the commit history now report not-applicable
  instead of open forever. From the founder's second round on the fixed box: the orientation walk
  waits for the identity beat instead of competing with it, you are asked your own name first, and
  a fresh Studio's first document passes its own validator.

*Stated plainly so nothing above reads as more than it is: the seven-beat first-day walk of these
exact bytes runs after publication, and its scores are published with the release retrospective,
not claimed here. The planned rename of the memory surfaces did not ship; every shipped reader
agrees with the current names. The full boundary is in `KNOWN-LIMITATIONS.md`.*

*If you are arriving from v1.95.0 or earlier: the update path is the box zip itself, applied with
`tropo-apply-image.py`; read its `plan` output before `apply`. Nothing here puts your Studio under
git, and nothing depends on it.*

---

*Tropo v1.96.0 | 2026-09-09 | Kernel-managed. Refreshed each release by the update pipeline. If you
are reading this inside a Studio, the version that matters is `.tropo/version.md`.*
