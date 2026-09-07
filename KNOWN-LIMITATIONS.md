# Known Limitations — read this before you evaluate

*This file exists because of a rule we hold ourselves to: declared absence costs nothing;
documented-but-broken costs everything. Everything below is a deliberate, known boundary of this
release — not a surprise you'll find on your own. If you find something broken that is NOT
listed here or documented elsewhere, that's a bug: tell us, and trust the box over the doc.*

## What this release does not do yet

**1. Federation — shipped between two, proven in rehearsal, walked in a box only at the fire.**
Two colleagues can share one vault: one owner-signed join, an authorship-aware publish boundary,
and a merge seam wired live with a gate that can still say no. The upgrade paths were rehearsed
and recorded on the previous run. The join ceremony walked end to end in a shipped box, with
nobody from Tropo present, is the condition this release fires on; it had not run when this was
written. Federation beyond two colleagues, cross-studio identity at org scale, is still ahead.

**2. Central administration.** There is no org-wide dashboard, fleet view, or central audit
surface. Each studio governs itself; its audit trail lives inside it (see `RELEASING.md` and the
event ledger under `vault/events/`).

**3. Org-standard distribution.** There is no supported way to push a policy, template, or
standard to many studios at once. `tropo-apply-image.py` updates one studio at a time; always
read its `plan` output before `apply` (a plan proposing large deletions deserves a second look —
`apply` takes a full backup first, so mistakes are recoverable).

**4. The update path — rebuilt and rehearsed, not yet applied live to a customer studio.** The box
zip is the update image, with a lift-and-replace path replacing a delivery channel that had
returned an error for every package after v1.86.0. The rehearsal of a customer upgrade on a fresh
clone was recorded on the previous run; the live upgrade of a real customer studio had not run when
this was written. Until it has, treat the documented apply-image procedure as the walked path.

**5. Your studio's inbox, for one release.** Shipped templates and capsules name the authoring
studio's inbox identifier as the fallback parent for a minted task, so a task you mint may parent
to an inbox your studio never has. Your studio mints its own inbox at first boot; the mint learns to
resolve it in v1.96. Until then, parent new tasks to a project of yours explicitly.

**6. Two rebuild shapes, one row.** A full index rebuild drops hub frontmatter keys (such as a
subsystem's home folder) that a single-entry rebuild keeps. The shipped Studio Map reads the hub
files themselves and shows the right picture; another reader of the index row may see the key
missing. Cured in v1.96.

**7. Cutting your own release: lock from `design`.** The plan-lock tool and the release preflight
disagree on which plan statuses are lockable; `design` is the only status both accept, and it is
how the last two releases were locked. Whether an entry ships is decided by the ship manifest,
not by the entry's `extraction_scope` field; an entry can say `ship` and still be withheld by
design. Both are recorded for v1.96.

**8. Test scope.** `npm test` in this box exercises THIS box: the in-box self-test, customer-mode
validation, and the studio smoke test (five real operations against your studio). The vendor's
full development suites are not shipped and their results do not apply to your studio.

**9. Vendor crew substrate.** The ship manifest decides what leaves the authoring studio, and this
release is the first whose candidates were built with it armed. This box ships no studio identity
of ours and none of our crew's identity records; the two companions it does ship, Cal and Darin,
are yours, minted as identity in your studio at genesis. If you find a record of ours that is not
Cal or Darin, that is a bug: report it.

**10. Residual documentation drift.** Before the box is sealed, a gate checks that every path a
shipped instruction file tells you to open exists in the box, and it read zero at the cut. Even
so, a residual doc-vs-box mismatch may exist in prose the gate does not read. The rule when you
hit one: **the box is the truth, the doc is the bug.** Report it.

**11. This release's own acceptance had not run when it was written.** The cold-stranger arrival
walk on the shipped box, the join-ceremony walk in the box (item 1), the release-mode validator
compare, the harness pass, the founder's external test and the cold-boot walk all happen on the
first sealed candidate, and publish does not fire until they carry passing records. This document is
the record of what is built; those runs are the record of whether it works where it is going.

**12. Your Studio is not a git repository, and nothing here puts it under one.** The box ships as
plain files. If you want history, branches, or a second machine, run `git init` yourself and commit;
from that moment the discipline the crew uses applies to you too, and the most useful half of it is
one line: fetch before you read, push after you land. Nothing in the Studio does this for you, and
nothing depends on it.

**13. After you mint your companions, the health check reports failures until you rebuild.** Genesis
writes new governed records; the index does not know them yet, so `tropo-validate.py --customer` can
report failures that are only staleness. The cure is `python3 vault/tools/tropo-rebuild-vault.py`.
Disclosed rather than hidden: that rebuild currently exits with code 8 from its own pre-check while
still completing its work, so judge it by its output and the validator run after it, not by the exit
code. Being fixed.

**14. A founder principal minted at arrival carries a placeholder the validator flags.** When you
mint yourself as founder, the record is created with an accountability-scope slot left empty for you
to fill. Until you fill it, the validator names it. That is the check working, not a defect, and the
cure is to write your own scope into the record.

---

*Tropo-OS v1.95.0 | This file is maintained per release. An honest boundary you can plan around
beats a silent gap you discover at the worst moment.*
