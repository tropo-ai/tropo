# Changelog

All notable changes to Tropo are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/tropo-ai/tropo/compare/v1.85.0...HEAD
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
