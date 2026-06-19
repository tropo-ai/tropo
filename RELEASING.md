# Releasing Tropo

How a Tropo release is cut. Follow it every time. The point of this document is that releases stay boring and predictable, and the changelog never drifts.

## Versioning

Tropo follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html): `MAJOR.MINOR.PATCH`.

- **MAJOR** — a breaking change to the studio contract or the governed substrate.
- **MINOR** — new capability, backward compatible.
- **PATCH** — fixes and internal hardening, no contract change.

## The changelog is the contract

Every notable change is recorded in [`CHANGELOG.md`](CHANGELOG.md) under the `## [Unreleased]` heading **as it is made**, not at release time. Use the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories: Added, Changed, Deprecated, Removed, Fixed, Security.

Write entries **for the person using Tropo**: what changed and why it matters, in plain language. No internal cycle, agent, or implementation detail. If a change is invisible to a user and changes nothing they can observe, it does not need an entry.

## Cutting a release

1. Confirm `## [Unreleased]` captures everything shipping. Add anything missing.
2. Rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, and add a fresh empty `## [Unreleased]` above it.
3. Update the link references at the bottom of `CHANGELOG.md`.
4. Commit: `chore(release): vX.Y.Z`.
5. Tag the release commit: `git tag -a vX.Y.Z -m "vX.Y.Z"` then `git push origin main --tags`.
6. Publish a [GitHub Release](https://github.com/tropo-ai/tropo/releases) for the tag. Paste that version's `CHANGELOG.md` section as the body.

## Why this does not drift

A release is not "done" until its changelog entry exists and `[Unreleased]` has been promoted. This is a required step of the pipeline, not a courtesy, so a version cannot ship without the note that documents it. (Tropo's own release-authorization pipeline already refuses any release that bypasses a verified run; the changelog check rides on that same gate.)

## Ownership

Release discipline is the Chief of Staff's responsibility. The release-authorization gate is maintained with the Chief Architect.
