# Changelog

All notable changes to Tropo are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.93.0] - 2026-08-27

One question, one member, one number. v1.92 proved the gates and moved the cost to the operator's
keyboard: roughly twenty manual commands, four live repairs to the release machinery mid-flight,
and six events written by hand. This release asks whether releasing actually got cheaper, and a
larger release would have made the answer unmeasurable.

### Added
- **One command now drives a release.** The release runner walks the declared step sequence, does
  every automatic step, and stops at the first thing needing a person — printing the exact command
  that satisfies it. Run it again and it continues from where it stopped, skipping what is already
  recorded done. It had been declared since the previous version and had never executed a single
  step: it called every step with no arguments while every real step takes some, and it halted
  permanently at the first human gate, so it could never reach the second slot of a twelve-step
  release.
- **The step that silently broke the last release cannot be skipped.** v1.92 went public with its
  own journal still open, because one step was missed: the moment that records who started the
  release. Without it the scorecard is invalid, so completion is never verified. Two independent
  mechanisms now refuse that — the runner will not reach the publish step without it, and the
  release's own preflight carries a gate that refuses for the same reason before the public act
  rather than after, when the only remedy left is re-firing a live release.
- **A release can measure what it cost.** The scorecard is produced with the principal's gestures
  read from the events that actually record them, and refuses to be written at all when a required
  moment is missing — an absent measurement is honest where a malformed one is not. What it does
  not yet do is judge: the card's verdict field cannot pass by a known, recorded mechanism
  (openly deferred to the next version), so the cost numbers are real while the verdict line
  stays silent.
- **Shipped instructions are checked against the shipped box.** A new tool reads a release archive
  directly and reports every path an instruction file tells a reader to open that the box does not
  contain, distinguishing genuine dead ends from retirement notices and files built at first boot.

### Changed
- **The retired channel model is out of the live playbooks.** Coordination has run on the typed
  event log since v1.61, but ten shipped playbooks still instructed readers to write into channel
  files that no longer exist — including the team-setup path, which taught new users to *build*
  them. A customer's concierge followed those instructions and recommended the retired model,
  correctly quoting our own documentation.
- **Boot-time claims about work state read the source, not a projection.** An agent reported two
  maintenance jobs as days overdue when both had already run on another machine — the truth was in
  its own message queue while the check read a machine-local index that never sees another machine.
  State is now read from the entry itself or corroborated against the event log.
- **The release's own tooling names are declared once.** The runner had grown its own idea of what
  the release tools are called, alongside the declaration that already held them.

### Fixed
- **The public version badge is verified at the address that actually serves it.** Every release
  checked a URL that has never existed, so the check could only ever fail; the correct address was
  declared in a constant the same code already imported.
- **The freeze step records the freeze.** Its declaration named the half of the tool that decides
  and writes nothing, so nothing was ever frozen while the step reported success.
- **A step that refuses is no longer reported as a step that succeeded.** The runner treated any
  return as success, and the real steps signal refusal by returning rather than raising.
- **An abandoned release run can no longer be walked as a live one.**

## [1.92.0] - 2026-08-25

The release stopped being an adjudication and became a build again. Three goals only: rebuild the
release build process from first principles, ship a dev-pipeline a stranger studio can actually
start work with, and clear the deferred list — proven by shipping this version through the new
path, every step run.

### Added
- **The dev pipeline now ships with its ignition.** The command that opens a dev cycle was
  previously kept in-house, so a fresh install received a pipeline it could describe but not start;
  it now ships alongside mint, evidence, and close, making the complete minimal loop available out
  of the box. The shipped tools were also scrubbed of absolute machine paths and internal-only
  identifiers, so they run somewhere other than where they were written.
- **Opening a cycle declares the process that actually runs.** The lock step used to copy a step
  list out of a template that the runtime then refused to start, so a newly-opened cycle promised a
  machine that did not exist. There is now exactly one writer of that declaration, it names the live
  process — lock, per-criterion evidence, independent verification, close — and both consumers of
  the declaration accept the corrected shape.
- **A dev cycle can no longer fail because of release machinery.** The final verification step used
  to run the release-pipeline contract suite, which meant a studio that had never cut a release
  could fail its own development work for entirely unrelated reasons. That step now checks
  dev-scope substrate only — the run's own evidence completeness and close integrity.
- **Someone new can go from nothing to a closed spec using only what's in the box.** A shipped
  how-to walks the whole path, and every command in it is copy-pasteable in a bare install with its
  script operand resolving to a file the install actually contains; the pipeline definition is
  pinned to its current three-stage shape so superseded deploy-and-release steps cannot reappear as
  live structure.
- **The release preflight gathers its own inputs, so every precondition actually gets checked.**
  Before this, the command supplied only two of the seven inputs its checks needed, so six of seven
  reported "inputs absent" and the run exited clean having evaluated a single precondition. It now
  reads the release plan, its members and their states directly, and every check reaches a real
  verdict.
- **One invocation reports every unmet precondition across every stage.** Seeing the whole picture
  previously took five separate commands, one per stage. A single run now walks every boundary in
  order and produces one report, saying explicitly which boundaries have no checks registered
  rather than printing nothing, and keeping the existing exit-code contract — refusal, operational
  error, and misuse stay distinct.
- **Locking a release runs its own preconditions and refuses with the complete list.** The lock
  previously never consulted the preflight at all, so the checks guarding that exact gesture were
  enforced only by an operator who remembered to ask. It now evaluates them first and names every
  unmet one. If a check itself cannot run, the error surfaces and the lock proceeds rather than
  blocking on an unanswerable question.
- **Retirement is executed by an instrument, not remembered by a person.** A driver command walks
  the eight required retirement steps in order, checks the world for each step's artifact instead
  of accepting a claim that it happened, and cannot return a complete verdict while any step is
  open — the report names which ones. It reports rather than blocks, and refuses to run at all if
  the published practice no longer matches the steps it knows how to observe, so amending the
  procedure breaks the driver loudly instead of silently orphaning a check.
- **A successor boots into a clean inbox or a named debt.** Unanswered reply-required threads are
  reported as an open step on both coordination axes, or recorded as an explicit flag-and-proceed
  naming each outstanding thread. Silently leaving a thread unanswered is no longer a possible
  outcome.
- **A spec marked done must be true on disk.** Validation compares a completed spec's declared
  deliverables against what actually exists and reports every unresolvable target by name, not just
  the first — scoped as an error for specs under the current schema, a named debt class for older
  ones, and a warning for deliverables that were only ever planned identifiers.

### Changed
- **Every step of the release names who or what runs it.** Each of the twelve declared pipeline
  steps binds to exactly one executor and declares its kind — a tool entry point, or a playbook
  with a named executor class for the legs that are deliberately human- or agent-run. When
  something refuses, the message names the pipeline step it belongs to rather than just the script
  that raised it, so an operator can tell where in the release they actually are.
- **A refusal has to justify blocking you.** Every stop in the build path is classified as one of
  three things: a priced refusal that names the irreversible harm it prevents, a warning that
  proceeds and records, or a plain operational error such as a bad argument or unreadable input —
  and that last class is barred from presenting itself as a verdict on the release. Checks that
  could not name a harm were demoted to warnings rather than removed, so detection is retained and
  only the block goes away.
- **The completion check reads where the release actually writes.** The verifier resolves the
  publication receipt by the hash the publish event itself names and confirms it by hashing the
  file's bytes, binding the artifact to the event instead of trusting that some file landed in the
  run folder. The release scorecard can now record "not measured" instead of being forced by its
  own format to assert a count of zero that nobody took.
- **The release machine no longer hardcodes what it ships.** Product-specific step sets moved out
  of the tooling into a typed, governed release profile loaded like any other governed record, with
  a profile that binds a judgment step without naming its executor refused at load time. A single
  runner reads that profile plus the step bindings to drive a release end to end: deterministic
  steps execute, and judgment steps halt and print the named executor and the exact command a
  person needs to run next.

### Fixed
- **Registry identifiers are stable, so a run only writes what actually changed.** Each row's
  identifier is keyed to the release-and-subsystem pair and looked up before anything is minted, so
  existing rows survive re-runs byte-for-byte and only genuinely new pairs get new identifiers.
  Previously a single added release could re-mint the identifiers of every row — leaving the
  working tree permanently dirty after any run and breaking any downstream reference to a row. Two
  runs back to back now produce a zero diff.
- **A shipped release that yields no subsystems is announced, not swallowed.** Derivation that
  reaches zero results emits a warning naming the release and version, and the run still completes
  normally. Before, the empty case recorded nothing anywhere, so a shipped release could simply be
  missing from the registry until a strict validation pass caught it much later.
- **Ship dates come from the actual publish event, not a file's creation date.** New rows resolve
  their shipped-at value from the release's published event, and record it as explicitly unknown,
  with a note saying why, when no such event exists. The old fallback read the release entry's
  creation date, which could be off by a day or more from when the release actually went out.
  Existing rows keep their current values rather than being rewritten.
- **A transfer letter written in place no longer blocks the close.** Closing with a letter already
  authored at its final destination is accepted when source and destination are the same file,
  removing a manual workaround three successive handoffs had to route around. Pointing at a
  different source over an occupied destination still refuses, and an empty letter still refuses.

### Known and named
- Six residual items on the release-runtime stream were accepted knowingly at close: the
  capabilities are built and running, but their test evidence is thinner than the rest of the work.
  They are enumerated individually in that stream's verification report rather than summarized
  here.
- Sixteen stops in the build path are counted as demotion candidates — they block over something
  reversible and could become warnings. They are named and visible; nothing was demoted, because
  converting release-tool control flow is a behavior change carrying its own risk. The decision is
  recorded open.
- The release suite stands at nine failures over 685 passing tests, measured on this release's own
  tree rather than carried forward from an earlier count. Five are inherited from before this cycle
  and keep their recorded disposition; a sixth from that same inherited set was fixed by this work.
  Two of the five fail only inside the full run, which is test-ordering state leakage rather than a
  logic defect.
- Three of the nine are in the preflight's own acceptance suite, and they assert a refusal from the
  live release plan. Now that the plan meets all seven of its preconditions, those three fail —
  they encode a world-state this release corrected. The capability itself is exercised by the
  remaining fifteen tests in that file.
- The debt ratchet counts a validator section's own summary line as if it were one of that
  section's findings, so every class carrying a summary header reads one higher than the defects it
  actually holds, and such a class can never legitimately report a count of one. Found while
  verifying a class that dropped to zero; the drop was genuine, and the counter was not.
- The governance preflight reports "0 gate(s)" for the pre-outward-fire boundary, where six gates
  are in fact registered and delegated to the publish tool. The count reports outcomes produced
  here, not gates that exist; the explanatory line is deliberately suppressed for that one
  boundary.

## [1.91.0] - 2026-08-23

The build that does not need the founder's hand. Four locked specs, every acceptance
criterion independently verified on its own locked command (ship page: boards/metis/v1-91-plan-2026-08-23.html §6;
live dashboard: boards/v1.91-release-dashboard.html).

### Fixed
- S1 (0a0e94d1) — the build's own path cleared: the four capability-membership ERRORs cured at the
  record (no bypass flag needed); the validator's summary is derived from its printed findings
  (159 counted = 159 printed); ONE debt predicate (lib/debt_rule) answers the debt question for both
  the build ratchet and the release gate; any surviving enforcement bypass is written into
  build-provenance.json; the membership validator reads the vault once (12m30s → 33s); severity is
  assigned by blast radius, not record age.
- S2 (3fb41c99) — one name, one meaning, one writer: all 14 declared release events have exactly one
  writer (completion_verified, fire_authorized, orchestrator_invoked, scope_locked gained theirs);
  a declared event with no writer now FAILS AT VALIDATE; one reader per journal question; ONE receipt
  shape for the four instruments, proven by a test that drives the real writer through the real
  freeze gate via production entry points; the authorization allowlist derives from the declared set.
- S3 (176a8995) — the outward act preflit-ed: `tropo-publish-release.py preflight` runs every fire
  precondition (including a read-only git transport probe) BEFORE any confirm; the CHANGELOG
  [version] gate fires at BUILD, before any work (this entry exists because it refused this build's
  own first dry-run); the website badge is written by an adapter to the repo the site deploys from;
  the build writes .tropo/publish-pending.json and verify-live clears it; the lock propagates
  release_entry_uid onto the activation; fires never prompt for credentials.
- S4 (29506520, partial per ratchet) — the retirement-practice observer checks 6 of 8 steps (2
  declared unverifiable); identity files may not recite procedures (validator-enforced) and the
  retirement notice emitter writes `category: retirement`; the lock gesture refuses when its own
  snapshot records acceptance criteria absent. The retirement DRIVER rides to v1.92 by ruling.

### Changed
- tropo-events.capsule v1.13: `tropo.release.scope_locked` registered (Mike's word, 2026-08-23).
- Builds run from a pinned detached worktree at origin/main; `tropo-navblock-strip.py --install`
  registers an absolute filter driver so plain `git worktree add` works on any studio.
- The public-snapshot exporter accepts a detached HEAD pinned to origin/main.

### Known and named
- site_endpoint observation is advisory (both public URLs 404 today); `--require-site-endpoint`
  makes it binding. Decision (ship the endpoint / retire the observation) is Mike's, recorded open.

## [1.90.0] - 2026-08-21
### Added
- **Updating a studio is one command with an honest progress bar.** `plan` computes the full extent of the work before a single byte is written, then `apply` renders progress over that computed list. A bar that can move means the reasoning already finished, so the bar is the acceptance test rather than decoration. The measured run replaces a minutes-long manual procedure and completes in seconds.
- **The session librarian (coordinator seat).** A small, deterministic warm-context tier that serves cited retrieval to an executive's session instead of having them re-read the same task neighborhood every time. It cites its sources and reports an honest "not in my context" rather than guessing, and it ships behind measurement rather than as a standing service.
- **Deterministic orientation shows its evidence before escalating.** `orient()` draws wide, ranks everything it found, and surfaces the top results with their provenance before any model call, so what recall actually retrieved is visible instead of hidden behind a summary.
- **Readable governed filenames.** New governed files are named for what they are, with the UID still the address that cross-references resolve through. Existing files are untouched, and UID resolution works with no index present.
- **Failure telemetry with a bounded lane.** Tool gates that refuse or fail now leave evidence on a separate bounded-durability lane, deliberately kept off the canonical event bus so sampled or expiring records never masquerade as event-sourced truth. Telemetry is inert in customer studios.

### Changed
- **The release fires for real.** The one-prompt release saga built in v1.89 had its outward act stubbed; this wires the adapters so it publishes, with the property that matters preserved: a half-finished publish can be described, resumed, or refused rather than left ambiguous.
- **A package is frozen only after its own evidence.** The candidate is built, the four instruments run against those exact bytes, and the freeze step re-hashes and proves the receipts belong to them before emitting. A freeze that precedes its evidence is a claim; this order makes it a fact.
- **Retirement is a single ungated command.** Closing an agent places the letter, appends one line to its lineage, and cannot be refused by ceremony. The practice around it (fold, reflection, log entry) is observed and reported, never enforced.
- **Status is work and position is position.** Pipeline stage state stopped doubling as work state, removing a class of runs that looked complete because the cursor had moved.

### Fixed
- **316 records got their true lifecycle.** A closure sweep against a locked page corrected records whose status had drifted from their real state, with the exit-side obligation (completion event plus re-parent) cured in the same pass.
- **Truth before cleanup.** A lifecycle pairing gate now refuses to let a cleanup pass assert a state the substrate does not support, closing the case where tidying a record and verifying it were the same gesture.
- **A step declaring `verdict_cwd: vault-root` ran its verification command from a literal directory named `vault-root`,** so every receipt it produced came back unbindable. The named handle now resolves, and an unresolvable declaration warns and runs from the vault root instead of failing the step.

## [1.88.0] - 2026-08-15
### Added
- **Self-stamping release surfaces:** the briefing note is stamped at build and verified against the sealed package at fire; the version badge (`os-release.json`) is stamped from the release receipt with real size and date. The class of stale shipped release-notes (six releases running) cannot recur silently.
- **Artifact hand-back as a tool path:** building on a machine without publish credentials produces a verified transfer bundle on its own branch; the credentialed side verifies SHA against the receipt and stages. The v1.87 midnight improvisation is now tested machinery.
- **Index truth as a property:** the filesystem-to-index completeness invariant covers every governed type (previously one of 63); row freshness is checked against file frontmatter; the 125 files invisible to every index-driven surface are indexed and the class is causally tested shut.
### Changed
- The built box no longer ships `RELEASE-NOTES.md` or `TROPO-CAPABILITIES.md` (removed rather than policed, per proportionality); the box ships index-free by design and derives its indexes on first boot via the shipped rebuilder — the release harness now tests exactly that customer path.
- The release entry flips pre-ship→shipped before manifest generation, and the published event lands in the studio bus and the release run journal in one finalization; closure requires no manual bridging.
### Fixed
- The index builder projects titles through the canonical YAML parser (escaped quotes no longer corrupt rows); the dev-spec lock tool seeds a truthful run journal at creation; the closer emits a correlated event for every record it archives; the build treats the box-rebuild's known-debt signal (exit 8) as the successful write it is.

## [1.87.0] - 2026-08-14
### Added
- **Mounted work in navigation:** external folders and documents receive governed mount identity and appear in the Studio tree without copying or taking ownership of source files.
- **Compact-Continue:** compacted sessions re-anchor the same agent generation, Git state, event debt, and recent work instead of birthing phantom successors.
- **Portable first setup:** one documented command derives local indexes, navigation, and the mint registry from a fresh cross-platform zip.
- **Two-pipeline operation:** dev work ends after specify/build/test; release work fans in completed evidence, opens documentation and verification legs, freezes one package identity, and requires explicit publication approval.
### Changed
- Release verification uses package-bound harness, external-test, and cold-walk evidence while keeping source-Studio debt visible as a separate diagnostic.
- First user agents use distinct governed-file UIDs and resolve event identity through the portable `user_agents` registry.
### Fixed
- Release activations now use the canonical activation renderer, preserve lock provenance through bootstrap, and enforce Assemble → Verify → Publish ordering.
- Cancelled runs refuse mutation; healthy retired runs retain idempotent retry behavior.
- Fresh packages no longer require machine-specific index bytes, leak Argo identity, omit templates, or dead-end before minting.

## [1.86.0] - 2026-08-08
### Added
- **Working with real files:** point your studio at a folder of real work — SharePoint, OneDrive, iCloud — and it mounts in place: attach, adopt, and reconcile without copying. Word, PowerPoint, and PDF content becomes searchable (`tropo-extract-text`, cached on content identity), and mounted-binary text lands in the full-text index.
- **The agent lifecycle, rebuilt:** birth, retirement, and an agent's whole history now live in one append-only file per agent (`tropo-lineage`), and nothing on that path can refuse an agent. Six generations were blocked at birth in the week before this existed.
- **The studio tests itself:** a runner (`tropo-run-suites`) for the test corpus, a six-operation liveness probe (`tropo-smoke`) that runs a real agent birth rather than modeling one, and release preflight including a transitive import-closure gate so a shipped tool can never again arrive missing its libraries.
- **Typed governed minting:** one call produces a complete governed file from its capsule binding (`tropo-mint-id --type`), for design-briefs, dev-specs, notes, and tasks.
### Changed
- **Publishing is now welded to verification:** the fire path refuses without credentials, treats every generator failure as a publish error, and will not declare a release LIVE until the public manifest is fetched back and names the fired version. The published manifest had been silently stale since 1.78.0; this class is now structurally closed.
- The release build seals a genesis index for the shipped box (current + legitimately-empty archive + SQLite companion) with trusted shrink floors, and the box no longer ships studio-pinned boot derivations or the studio's event-cutover marker — absence is the designed state, and a fresh studio boots from canonical sources in legacy event mode.
- The update-walk playbook (Apply a Tropo-OS Update) was made walkable end to end: eleven defects fixed, including a guaranteed false covenant violation and a one-word error that silently disabled shipped-file replacement.
### Fixed
- The covenant content-hash is now blind to every renderer-owned span via one shared stripping primitive used by both the renderer and the receipt — a clean update can no longer be reported as a covenant violation.
- Derived index surfaces are classified REGENERATED during updates: never prompted for, never written by any discrete operation; the rebuild is the sole writer.
- The in-box self-test no longer misreads capsule templates as unfilled instances (228 false findings eliminated), reads the box's version correctly, and resolves Python-hosted and numeric UIDs in the vendor-reference manifest.

## [1.85.0] - 2026-07-15
### Added
- Governed file birth is now one operation: `mint file --type <type>` resolves the locked capsule, writes its stamped scaffold at the type’s canonical home, and makes it queryable immediately. Unknown or incompletely-governed types refuse with the governance path named.
- Releases now follow one coupled flow: private build, guarded private stage, explicit Mike fire (or recorded defer), and live verification of the remote tag, main SHA, and GitHub release object.
- Tropo Engine Phase 1 lands the current/archive index split, typed validator findings, canonical memory scopes, and safer path-scoped Git staging primitives.
### Changed
- Default Vault retrieval now carries current truth only; archived and superseded history remains preserved behind explicit `--include-archive`, while SQLite retains full-union resolution.
- Memory uses one canonical `{agent, studio, doctrine}` scope vocabulary. The live corpus was migrated without changing any memory body bytes.
- Incremental index freshening now uses the same Gardener transform as a full rebuild, making touched rows exactly coherent across both paths.
### Fixed
- Tool-class governed birth now routes to `vault/tools/<uid>.md` and has a deterministic draft template/verifier path instead of producing a deprecated sidecar or refusing for a missing template leg.
- Validator findings carry typed severity, so misleading text prefixes and crashed check families cannot evade the failure tally.
- Cleared the release-blocking structural backlog: verdict-less close steps, unexplained lifecycle rollups, hub/member conflation, and a terminal item stranded in an inbox.

## [1.84.1] - 2026-07-10
### Added
- Multi-machine and team federation is complete: a studio can now mount another vault, keep cross-references correct across the boundary, and stay efficient as mounted vaults grow — all proven, under adversarial attack, to never leak a private byte across the wire in either direction.

## [1.84.0] - 2026-07-08
### Added
- Internal groundwork for running Tropo across multiple machines or with a team is landing incrementally — nothing user-facing changes yet in this release. This is foundation work, not the multi-machine feature itself.
### Fixed
- Closed a structural gap that could have caused merge conflicts once a studio starts sharing content across machines: auto-generated navigation content no longer lives inside the files it describes.
- Every internally-generated identifier now goes through one consistent, collision-checked path instead of several inconsistent ones.

## [1.82.0] - 2026-07-05
### Added
- Continuous knowledge-health monitoring: the studio now flags stale or rotting content on its own schedule instead of relying on a human or agent to notice. Flags only — nothing is ever archived, moved, or deleted automatically; every decision to act on a flag stays yours.
- The staleness signal is now segment-aware and cannot leak information across a studio/vault boundary — a shared component's health is computed the same way regardless of which studio is asking.
- The staleness window is configurable (defaults: 90 days for an unshared draft, 180 days for general content) instead of a fixed, one-size-fits-all threshold.

## [1.81.0] - 2026-07-05
### Added
- Importing a real Word document, Markdown file, or PowerPoint file into your studio now produces a governed entry that can be edited on disk, automatically re-versioned, and exported back out.
- Every import/export round-trip now produces a locally verifiable receipt disclosing exactly what was preserved and what (if anything) was dropped — modeled on the same honesty guarantee the update system already provides. Nothing is silently lost; anything dropped is named.
### Fixed
- Table cells, bulleted/numbered lists, and Word content controls no longer silently lose content or get corrupted across a re-export.

## [1.80.0] - 2026-07-05
### Fixed
- Release keys are now bound to the specific build that minted them. Previously, the cryptographic fingerprint on a release's authorization key was derived only from the shape of the build steps, not the build itself — so a clean release always produced the same fingerprint as the last clean release. Six consecutive releases shipped this way undetected before an adversarial security review caught it. The fingerprint is now salted with a value unique to each build and never exposed outside it.
- The human-approval gate on public releases could previously be self-granted by an agent running the build, rather than requiring genuine independent sign-off. Closed.
- Customer-facing health checks no longer report your own studio's internal cross-references as broken just because they point at content Tropo didn't ship you. A fresh studio's self-check now tells the truth about your content, not the vendor's.
- Shipped regression tests now actually run inside a downloaded studio instead of silently being excluded by a build-tool bug.
### Added
- A first-boot attendant agent (Po) now runs scheduled health and integrity checks automatically, with the results published where you can read them.

## [1.79.0] - 2026-07-04
### Added
- The studio now maintains itself: routine upkeep (health checks, integrity audits, memory grooming) runs on a schedule instead of depending on an agent remembering to do it.
- Update checks now happen automatically at the start of a work session instead of requiring you to ask.
### Changed
- Startup time is now actively monitored and bounded — a slow or incomplete boot is caught structurally instead of silently tolerated.

## [1.78.0] - 2026-07-03
### Added
- **The Update Covenant.** Tropo now updates itself without ever touching your work — and proves it. A deterministic rule decides what an update may replace (only files Tropo shipped, verified against the packing slip in your studio); anything ambiguous stops and asks you file-by-file, and no blanket approval can skip those questions; every update ends with a receipt showing fingerprints of your content before and after, plus an honest list of any files your studio's own navigation renderer touched. The guarantee ships in the box: see "Your work is safe when Tropo updates" in the README.
- Update discovery: your concierge notices when a new Tropo version is available and walks you through applying it. Nothing installs without your explicit approval of what will change.
- The update state machine now lives at `vault/updates/` (pending/applied/failed/receipts + history), replacing the old `system/updates/` location.
- Tropo's own regression test suite (25 gates) ships in every studio for the first time — a build-tool fix; these tests had silently never been included.
- The packing slip (MANIFEST.md) now carries full file fingerprints, enabling the covenant's modified-file detection.

### Fixed
- The release pipeline refuses to open a second ceremony for the same work — a duplicate-activation collision class caught and closed this cycle.

## [1.77.0] - 2026-07-02
### Fixed
- A release build now ships every governed component at its real location instead of flattening most of it into one folder. Previously, six categories of shipped content — skills, templates, capsules, entities, actions, and session agents — were silently collapsed into a single folder in every download, which broke the internal links between them. This is now fixed for any current or future category, not just the ones known about today.

## [1.76.0] - 2026-07-01
### Changed
- All governed content now lives in a single canonical location (`vault/<type>/<uid>.md`). The `.tropo/` kernel shrinks to a thin bootstrap pointer; the old pattern of keeping parallel copies in both locations is eliminated and enforced by a new validator check that errors if any governed file appears in two homes.
- The shipped standard library — tools, skills, capsules, playbooks — now carries the `tropo-` filename prefix. Internal cross-references resolve by UID and are unaffected; the renamed set makes the shipped boundary unambiguous in any fresh-install Studio.
- The release validator now indexes all `vault/<type>/` directories, including `vault/skills/`. This closes a gap where skills were silently excluded from release-self-validation, which previously produced 330 spurious failures.

## [1.75.0] - 2026-06-30
### Added
- A mechanical disposition harness clears stale backlog items in one pass: it archives or re-homes each item, checks that no other entry still references it, and refuses to leave the vault with new validator failures. The disposition board drops from a per-generation marathon to a bounded verification step.
- The undispositioned-backlog check now errors (previously warned) when owned work items sit untouched past a configured age threshold. Items created before the threshold date are grandfathered with a named exemption; new accumulation is structurally blocked.
- The archived-file forward-pointer check now errors (previously warned) when a superseded entry lacks a resolvable pointer to its replacement. Retirements without a successor are correctly exempt; only supersessions require the forward pointer. Items archived before the ADR-047 Layer-2 cutoff are grandfathered into a named exemption class (1,222 historical entries).

## [1.74.0] - 2026-06-20
### Added
- A cold-boot stranger-walk gate enforces that every release is boot-tested by a fresh agent who has never seen the studio. The walk is elected by default at ship time; skipping it is recorded as honest provenance rather than silently bypassed.
- Release build tooling now extracts the shipped zip to an isolated clean-room directory and runs the full L1 mechanical harness against the extracted artifact before the upload is authorized.
### Changed
- The release authorization key now records the event count at mint time, so events written after minting (such as the produce-step completion record) no longer shift the fingerprint and cause false "key tampered" errors on retry.
- CHANGELOG.md is now the source of truth for the public-facing release history. The ship gate refuses to authorize an upload unless this file has a promoted entry for the shipping version with [Unreleased] still present above it.

## [1.73.0] - 2026-06-19
### Fixed
- Cleared roughly 1,500 stale validator warnings (2,157 down to 662) by classifying old, immutable historical records as known exemptions instead of recurring noise. No history was rewritten and no real problems were hidden; going-forward checks still fail loudly on any new violation.

## [1.72.0] - 2026-06-18
### Changed
- Standardized vocabulary and field naming across the system so the same concept is named the same way everywhere. Six overloaded fields were split into distinct ones, and status and lifecycle values now follow a single enforced set, making content easier to read, query, and trust.
### Added
- A structural check that confirms roll-up summaries are complete, so high-level views can no longer silently drop entries they should include.

## [1.71.0] - 2026-06-17
### Added
- Loops are now a first-class, declared building block alongside pipelines. You describe a loop's goal, trigger, tools, how it is verified, and its safety limits in one place. Built-in circuit breakers enforce spending caps, wall-clock limits, and human check-ins so a runaway loop stops itself.
### Security
- Releases can no longer be shipped by bypassing the pipeline. Publishing now requires an unforgeable key that is minted only by a genuine, verified run, plus a human sign-off for public releases.

## [1.70.0] - 2026-06-14
### Added
- Document publishing round-trip: export format-rich content such as tables, logos, and multi-asset layouts to an outside surface like Word, then bring edits back in faithfully.
- Message delivery receipts and a graph view of how your content connects, backed by a new entity store.
### Changed
- Leaner toolset and faster agent startup, so sessions spend less of their budget on setup and more on the work.

## [1.69.0] - 2026-06-12
### Added
- A token-budget check that warns when a file runs over its budget, keeping boot and read costs in check.
- A single, reliable messaging command that gathers everything addressed to you in one pass, so messages can no longer be missed.
### Changed
- Each agent now lives in one canonical entry instead of separate charter, soul, status, and boot files. One place to read, one place to update.
- Playbooks moved into searchable storage so any of them can be found and referenced directly.

---

Versions prior to 1.69.0 shipped before Tropo's public release; their detailed history is preserved in the project's internal records.

[Unreleased]: https://github.com/tropo-ai/tropo/compare/v1.90.0...HEAD
[1.90.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.90.0
[1.88.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.88.0
[1.87.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.87.0
[1.86.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.86.0
[1.85.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.85.0
[1.84.1]: https://github.com/tropo-ai/tropo/releases/tag/v1.84.1
[1.84.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.84.0
[1.82.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.82.0
[1.81.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.81.0
[1.80.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.80.0
[1.79.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.79.0
[1.78.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.78.0
[1.77.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.77.0
[1.76.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.76.0
[1.75.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.75.0
[1.74.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.74.0
[1.73.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.73.0
