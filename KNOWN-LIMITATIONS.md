# Known Limitations — read this before you evaluate

*This file exists because of a rule we hold ourselves to: declared absence costs nothing;
documented-but-broken costs everything. Everything below is a deliberate, known boundary of this
release — not a surprise you'll find on your own. If you find something broken that is NOT
listed here or documented elsewhere, that's a bug: tell us, and trust the box over the doc.*

## What this release does not do yet

**1. Federation — shipped between two, proven in rehearsal, walked in a box only at the fire.**
Two colleagues can share one vault: one owner-signed join, an authorship-aware publish boundary,
and a merge seam wired live with a gate that can still say no. The upgrade paths were rehearsed
and recorded on an earlier run. This release does not claim the join ceremony walked end to end in
a shipped box with nobody from Tropo present. Federation beyond two colleagues, cross-studio
identity at org scale, is still ahead.

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
to an inbox your studio never has. Your studio mints its own inbox at first boot. The previous
edition of this file said the mint would learn to resolve it in v1.96; it did not, and this edition
says so. Until it does, parent new tasks to a project of yours explicitly.

**6. Two rebuild shapes, one row.** A full index rebuild drops hub frontmatter keys (such as a
subsystem's home folder) that a single-entry rebuild keeps. The shipped Studio Map reads the hub
files themselves and shows the right picture; another reader of the index row may see the key
missing. The previous edition said this would be cured in v1.96; it was not, and the record that
tracks it is still open. Still true in this release.

**7. Cutting your own release: lock from `design`.** The plan-lock tool and the release preflight
disagree on which plan statuses are lockable; `design` is the only status both accept, and it is
how the last three releases were locked, this one included. Whether an entry ships is decided by
the ship manifest, not by the entry's `extraction_scope` field; an entry can say `ship` and still be
withheld by design. Both are still true in this release.

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

**11. The first-day walk of this release's shipped bytes runs after publication.** The seven-beat
cold-stranger walk (unzip, boot, first message, health check, mint a companion, retire it, come back
tomorrow) was scored on an earlier candidate of this release, where it found the prose defects this
release fixes; the walk of the published box itself runs after the fire, by the founder's decision,
and its scores are published with the release retrospective rather than claimed here. The
release-mode validator, the box's own self-test and the health check on a copy of the candidate
did run before the fire. This document is the record of what is built; that walk is the record of
whether it works where it is going.

**15. The memory-surface rename did not ship.** The planned rename of the live memory files to
`memory.md` and `memories.jsonl` at both scopes was cut from this release by decision; the shipped
surfaces keep their current names, and every shipped reader agrees with them.

**16. The candidate that was verified and the bytes that shipped differ by two small landings.** The
walk box for this release was built from one named commit; the release was built from the tree a
few commits later, and the whole difference is enumerated on the release plan: a merged refinement
of the retirement driver (a broken crew-brief link is not mistaken for an absent brief) and one
reworded sentence in the concierge's failure path. Nothing else moved between the two.

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

**14. Your founder principal is minted with a default accountability scope.** When you mint
yourself as founder at arrival, the record's accountability-scope section is filled with a default
sentence (signoff on locks and ratifications, the retirement signal, approval of agent scope changes
and new agents, acceptance of governance changes). It is yours to edit. Earlier candidates of this
release left that slot as a placeholder the validator flagged on your very first health check.

**17. Answered-state on the bus does not work in a fresh Studio.** `tropo-check-events.py` decides
whether a `reply_required` request has been answered by keying on each event's `event_uid`, and no
event a fresh Studio emits carries one yet, so a reply sent without `--final` is treated as terminal
and `--not-final` has no effect. Found by a companion on its first day and verified in source. The
practical rule for now: mark a reply `--final` only when the thread is really closed, and read the
thread yourself before treating a request as answered. The cure lands in the next release. The
emit tool's own output prints an `event_uid` that the ledger does not persist; trust the record,
not the print, until then.

**18. What the founder's own two-round test of this box found and did not fix.** Before this
box was sealed, Tropo's founder drove a candidate of it cold, twice, with three agents doing real
work over the bus. Seven first-minute defects from round one and six from round two are fixed in
these bytes. Ten are not, by decision, and are named here so you meet them as known: the first
greeting takes minutes on a fresh box, not the thirty seconds the entry file promises (index build
and genesis); the read observer counts the file-reader tool, not the reading, so an agent that
reads with shell commands is reported as not having read, and an agent that never opens the
window reports nothing at all; the two authoring scanners flag a mint token or a placeholder quoted
inside a fenced code block, so the Studio cannot cleanly document its own template grammar; the
concierge never claims her own genesis placeholder, so a roster built from lineage files shows her
model as placeholder text; the 500-character event body cap is documented and not enforced; the
mint tool refuses `--title` on more types than its help suggests; the resident marker holds one
agent, so three agents in one folder cannot all be represented; and the L0 project registry the
"verify against canon" rule points at does not ship. None of these loses your work.

---

*Tropo-OS v1.96.0 | This file is maintained per release. An honest boundary you can plan around
beats a silent gap you discover at the worst moment.*
