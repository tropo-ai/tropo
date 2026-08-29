# Known Limitations — read this before you evaluate

*This file exists because of a rule we hold ourselves to: declared absence costs nothing;
documented-but-broken costs everything. Everything below is a deliberate, known boundary of this
release — not a surprise you'll find on your own. If you find something broken that is NOT
listed here or documented elsewhere, that's a bug: tell us, and trust the box over the doc.*

## What this release does not do yet

**1. Federation.** This box is a single, sovereign studio. Cross-studio identity, shared team
vaults, and multi-person federation are the headline of the next release — designed, in build,
not here yet. Today, two people means two independent studios.

**2. Central administration.** There is no org-wide dashboard, fleet view, or central audit
surface. Each studio governs itself; its audit trail lives inside it (see `RELEASING.md` and the
event ledger under `vault/events/`).

**3. Org-standard distribution.** There is no supported way to push a policy, template, or
standard to many studios at once. `tropo-apply-image.py` updates one studio at a time; always
read its `plan` output before `apply` (a plan proposing large deletions deserves a second look —
`apply` takes a full backup first, so mistakes are recoverable).

**4. Guided updates.** This release's box zip IS the update image. The guided, in-studio update
walk arrives with the next release; until then, updating follows the documented apply-image
procedure by hand.

**5. Test scope.** `npm test` in this box exercises THIS box: the in-box self-test and
customer-mode validation. The vendor's full development suites are not shipped and their results
do not apply to your studio.

**6. Vendor crew substrate.** This box carries identity records of the vendor's own agent crew
(the Studio's souls and charters). Known, harmless to your studio's operation, and being
curated behind a default-deny ship manifest in the next release.

**7. Residual documentation drift.** A 1,615-claim audit of every shipped document ran against
this exact box before release. Even so, a residual doc-vs-box mismatch may exist. The rule when
you hit one: **the box is the truth, the doc is the bug.** Report it.

---

*Tropo-OS v1.93.0 | This file is maintained per release. An honest boundary you can plan around
beats a silent gap you discover at the worst moment.*
