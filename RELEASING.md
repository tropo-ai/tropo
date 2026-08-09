# Releasing Tropo

*One flow, two human gestures. Nothing goes public until a human fires it; nothing claims LIVE until the remote confirms it; nothing stays silently unpublished.*

This procedure covers `tropo-publish-release.py`, the Tropo-OS publisher for GitHub and distribution channels. It does not cover `tropo-publish.py`, the federation team-vault publisher.

## The flow

### 1. Build — private

```bash
python3 vault/tools/tropo-build-release.py --bump <patch|feature|release>
```

The build produces the release folder and zip locally. It uploads nothing. Its publish-state preflight reports existing drift, refuses anomalous state, and records an explicit offline build.

### 1.5 Verify — before you sign

The pipeline's external-test step verifies the build before signoff. Verify the right things: the build is **not byte-reproducible**. It embeds wall-clock timestamps (in the manifest, `version.md`, and build provenance) and packages the zip with file modification times, so two builds of identical source produce **different** zip and manifest digests. A release's recorded `sha256` values are therefore **fixity** digests — they prove the integrity of that one artifact **on the host that built it**. They are not reproducible by rebuilding elsewhere, and "reproduce the recorded digest" is not a valid cross-machine acceptance check.

To verify a build — especially one you did not produce yourself (another machine, a teammate's clone) — check three things, never the digest-across-machines:

1. **Content-equivalence.** Rebuild from the release's recorded source commit and confirm the substrate is green: `tropo-validate.py` reports 0 failed, and `tropo-rebuild-vault.py` exits 0. This proves the shipped content is sound, independent of packaging timestamps.
2. **Fail-closed evidence.** Confirm the release machinery *refuses* on a red validator, a missing pipeline-activation key, or a stale/uncurrent substrate — and that the refusal is not bypassable. Observing a guard fire is positive evidence the gate works.
3. **Fixity — on the build host only.** Verify a recorded `sha256` against the canonical artifact on the machine that built it. That is the only place the digit-for-digit match is meaningful.

*(A future deterministic build mode — pinned timestamps and normalized archive mtimes — would make digest reproduction a real cross-machine gate. Until it ships, do not write "reproduce the digest" into any acceptance criterion.)*

### 2. Sign — Mike's first gesture

Mike supplies the human signoff through the pipeline ceremony. The builder cannot grant this approval to itself. Signoff follows verification, not the reverse.

### 3. Stage — still private

```bash
python3 vault/tools/tropo-publish-release.py --version X.Y.Z
```

Stage:

- synchronizes the release extract into the publish clone;
- preserves repository-community files;
- prints and validates every would-delete path;
- requires the extract and source `CHANGELOG.md` files to match;
- commits and tags locally;
- disables the clone's push URL as a physical guard; and
- records the staged commit, tag, and version.

Nothing is public after staging.

### 4a. Fire — Mike's second gesture

```bash
python3 vault/tools/tropo-publish-release.py --version X.Y.Z --fire
```

Fire requires an interactive terminal confirmation whose default is **No**. Piped input is refused. It re-runs the outward gate, refuses a stale stage, then:

1. pushes main and tags;
2. creates the GitHub Release with the zip asset;
3. uploads the Supabase zip and update manifest; and
4. verifies the live remote tag, main commit, and release object.

Only complete remote proof earns `publish_state: live`.

### 4b. Defer — Mike's alternative gesture

```bash
python3 vault/tools/tropo-publish-release.py --version X.Y.Z --defer
```

Defer uses the same interactive discipline. It records who deferred, when, and why. A deferred release stays fireable later and does not produce a recurring boot warning.

## Named outcomes

| State | Meaning | Cure |
|---|---|---|
| `STAGED` | Committed and tagged locally; push disabled; nothing public | Fire or defer |
| `STALE-STAGE` | Publish clone moved after staging | Re-stage |
| `PUSHED-NO-RELEASE` | Push landed but GitHub Release creation failed | Re-fire; the operation is idempotent |
| `POSTED-UNVERIFIED` | Public action occurred but remote proof was unavailable | Re-fire through the verify-only path |
| `live` | Remote tag, main commit, and release object all confirmed | Done |
| `deferred-by-mike` | Mike explicitly deferred this version | None; it remains fireable |

A built release that is neither `live` nor `deferred-by-mike` is drift. Drift remains visible at boot and at the next build preflight.

## Changelog discipline

Write changes under `## [Unreleased]` in `CHANGELOG.md` as they land. Before build, promote them to `## [X.Y.Z] - YYYY-MM-DD` and update the comparison links. Stage checks that the release extract's changelog exactly matches the Studio source; rebuild is the cure for divergence, never a hand-sync.

## Attested-class releases

An attested-manual release has no normal pipeline run, so the coupled stage/fire path refuses it. Mike performs that release manually, then records remote proof with:

```bash
python3 vault/tools/tropo-publish-release.py --version X.Y.Z --verify-only
```

## Network boundary

An offline build is allowed and records `publish_state: UNKNOWN`. Fire has no offline mode: a public act requires the public network, and LIVE requires remote truth.
