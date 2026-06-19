# Changelog

All notable changes to Tropo are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/tropo-ai/tropo/compare/v1.73.0...HEAD
[1.73.0]: https://github.com/tropo-ai/tropo/releases/tag/v1.73.0
