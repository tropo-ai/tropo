---
uid: null
title: "Tropo Shard-Index Cache — Schema Reference"
status: locked
type: schema-reference
tier: os
schema_version: 1
owner: talos
created: '2026-07-08'
modified: '2026-07-08'
refs:
 - path: "vault/files/c6f6bea4.md"
   title: "Shard-keyed incremental composed index (ADR-051 Fork 4)"
 - path: "vault/files/18059aef.md"
   title: "ADR-051"
 - path: "vault/files/409ef1cc.md"
   title: "Mount-gate + compose-lockfile (the pin this shard cache keys on)"
 - path: "vault/files/4275b01c.md"
   title: "Cross-vault member_of (composes on the same composed index; segment tags preserved unchanged)"
---

# Tropo Shard-Index Cache — Schema Reference v1

*The authoritative schema for the per-vault shard cache (`.tropo-studio/shards/`) that makes composed-index (`vault/00-index.jsonl`) rebuilds incremental per mounted vault.*
*Locked v1 on 2026-07-08 by Talos T26, per dev-spec [c6f6bea4](../../vault/files/c6f6bea4.md) implementing [ADR-051](../../vault/files/18059aef.md) Fork 4 (Argus A128 rulings).*
*Style mirrors [`compose-lockfile-schema.md`](compose-lockfile-schema.md) in this folder.*

---

## Overview

Today the composed index (`vault/00-index.jsonl`) rebuilds by reading **everything** from source on every run. The shard-index cache makes that rebuild **incremental per vault**: each vault's contribution to the composed index is cached as a **shard**, keyed by the exact git commit the compose-lockfile ([compose-lockfile-schema.md](compose-lockfile-schema.md)) already pins. A shard whose pin hasn't moved is **reused**, not re-derived. Shards are unioned into the same `vault/00-index.jsonl` — the composed-index location is unchanged; the shard cache is purely an internal build artifact, not a new query surface.

**Location:** `<studio-root>/.tropo-studio/shards/` (one `.jsonl` + one `.meta` file pair per mounted `vault_uid`).

**Format:** JSONL for the shard's rows (matches `vault/00-index.jsonl`'s own line-per-record shape — a shard is literally a slice of that file, cached), JSON for the `.meta` sidecar (a single small object, matching `compose.lock`'s JSON choice for the same "human-legible small state" reasoning).

**Written/updated exclusively by:** `vault/tools/tropo-rebuild-index.py` (via the shared `vault/tools/lib/shard_index.py` module). Never hand-edit — a stale hand-edited `.meta` claiming a commit the `.jsonl` doesn't actually reflect is exactly the failure mode the staleness guard (below) exists to catch; hand-editing defeats its own purpose.

**Read (validation only, never written) by:** `vault/tools/tropo-validate.py`'s `check_shard_index_consistency` — the staleness guard. Same `lib/shard_index.py` module, so the writer and the validator can never silently disagree about what "stale" means.

**Regenerable / gitignored (signed I5 — derived-never-syncs):** the entire `.tropo-studio/shards/` directory is untracked (`.gitignore`, "Regenerable derived index" block). Deleting it entirely and running a full rebuild reconstructs every shard from source and reproduces a byte-identical `vault/00-index.jsonl` — the cache is never a hidden source of truth.

---

## The two shard populations

| Population | Pinned? | Trigger | Cache? |
|---|---|---|---|
| **Local shard** — this studio's own `vault/` (its `private` + `os` segments) | No — it is the working repo, not a mount | Existing full source-scan, every rebuild | Not cached under `.tropo-studio/shards/` — it is always freshly derived from `vault/files/` (+ the other 11 local collectors) exactly as `rebuild_index()` did before this dev-spec |
| **Mounted shards** — one per `vault_uid` in `.tropo-studio/compose.lock` | Yes — keyed by that record's `resolved_commit` | Only re-derived when the pin changes (or the cache is missing/stale) | `.tropo-studio/shards/<vault_uid>.jsonl` + `.meta` |

Only the mounted population is incremental; the local shard's cost was already small enough (~1-2s per the tool's own docstring) that pinning it would add complexity — and it correctly has no pin, sitting outside the compose-lockfile — with no reuse benefit (it changes on every local edit by definition).

---

## Shard key contract

**The shard key is `(vault_uid, resolved_commit)` — taken directly from `.tropo-studio/compose.lock`. No independent hashing.** The mount-gate's pin ([compose-lockfile-schema.md](compose-lockfile-schema.md) `resolved_commit` field) is the ONE dirty-check key; the shard cache does not compute or store any second fingerprint of a mounted vault's content. This is a deliberate ruling (Argus A128): the mount-gate already refuses to record a pin for a dirty or unpinned working tree, so the working tree AT `mount_path` IS the pinned commit's content by construction — re-deriving from `mount_path`'s current working tree when the pin has moved is safe and sufficient; there is nothing a second hash would catch that the mount-gate's own dirty-check didn't already guard.

---

## File shapes

### `<vault_uid>.jsonl` — the shard's index rows

One JSON object per line, in the **exact same per-record shape** `vault/00-index.jsonl` itself uses (each row is a raw record dict — `uid`, `type`, `title`, ... — as produced by `process_file()`, with a `path` field relative to the shard's own `mount_path`, mirroring the local shard's v1.69 path-provenance convention). No wrapper object, no shard-specific envelope — a shard's `.jsonl` is literally "the subset of `vault/00-index.jsonl` this vault_uid would contribute," cached.

```json
{"uid":"a1b2c3d4","type":"task","title":"...","path":"vault/files/a1b2c3d4.md", ...}
{"uid":"e5f6a7b8","type":"decision","title":"...","path":"vault/files/e5f6a7b8.md", ...}
```

**Important:** rows in the shard cache are **pre-segment-tag** (the `segment` field is NOT set at shard-derivation time). Segment discrimination (`apply_gardener_pass` / `discriminate_segment`, `vault/tools/lib/gardener.py`) runs ONCE, over the full unioned record set (local shard + every valid mounted shard), exactly as it does today for the single-source case. This is why the union must happen BEFORE the Gardener pass, not after — caching a post-Gardener `segment` value inside a shard would freeze that vault's segment tag at derivation time even if the studio's segment-discrimination rules (ship-manifest membership, `extraction_scope` backfill heuristics) evolve between rebuilds. Segment tagging is always a property of the CURRENT rebuild's full composed view, never a property baked into a shard.

### `<vault_uid>.meta` — the pin-diff record

```json
{
  "vault_uid": "<8-char-hex>",
  "resolved_commit": "<the resolved_commit this .jsonl was derived at>",
  "derived_at": "<ISO 8601 UTC timestamp of the derivation run>",
  "record_count": 42
}
```

- **`resolved_commit`** — required. Compared byte-for-byte against `compose.lock`'s current `vaults.<vault_uid>.resolved_commit` on every rebuild. Equal ⇒ REUSE the `.jsonl` verbatim, zero re-derivation. Not equal ⇒ re-derive both files.
- **`derived_at`** — advisory audit trail (when this shard was last actually re-derived, not merely reused).
- **`record_count`** — advisory sanity/debugging aid (matches the `.jsonl` line count at write time).

---

## The incremental rebuild algorithm

On every rebuild (`tropo-rebuild-index.py`, both dry-run and `--apply` — the reconciliation READS + conditionally derives regardless of `--apply`; only the FINAL `vault/00-index.jsonl`/sqlite writes are `--apply`-gated, same as every other source today):

1. **Derive the local shard** from `vault/` exactly as before this dev-spec (Sources 1–12, unchanged).
2. **For each `vault_uid` in `compose.lock`:**
   - Read `.tropo-studio/shards/<vault_uid>.meta`. If its `resolved_commit` equals `compose.lock`'s current pin for that `vault_uid` — **REUSE**: read `<vault_uid>.jsonl` verbatim, contribute its rows to the union, re-derive nothing.
   - Otherwise (`.meta` absent, or its `resolved_commit` differs from the pin): the shard is stale or new. If `mount_path` resolves to a reachable directory containing `vault/files/` — **RE-DERIVE**: scan `<mount_path>/vault/files/*.md` with the same `process_file()` transform the local shard uses, write a fresh `<vault_uid>.jsonl` + `.meta` (atomic temp+swap, same pattern as `vault/00-index.jsonl` itself), contribute the freshly-derived rows to the union.
   - If `mount_path` is ALSO unreachable — **CANNOT-COMPOSE** (the staleness guard, below): this vault_uid contributes ZERO rows to this rebuild. Never served stale, never silently skipped without a trace.
3. **Retire** any cached shard (`.tropo-studio/shards/<uid>.*`) whose `vault_uid` is no longer a key in `compose.lock` (an unmount) — its files are deleted; it contributes nothing.
4. **Union**: local shard rows + every REUSED/RE-DERIVED mounted shard's rows become the single `records` list that flows into the existing dedup (S7 source-precedence) → Gardener segment-tagging pass → `vault/00-index.jsonl` write, completely unchanged from how the pre-shard-index rebuild processed its single `records` list. A pure per-shard concatenation — segment tags are assigned AFTER the union (see "pre-segment-tag" note above), never carried inside a cached shard, so the union step itself cannot rename or drop a segment field it never touches.

`rebuild --only <uid>` (the record-level freshen path) is **unchanged** — it continues to target the local shard / live SQLite only, exactly as before.

**Zero mounts (today's real-studio universal case):** `compose.lock` is absent or has an empty `vaults: {}` — step 2 has nothing to iterate, step 3 has nothing to retire (no cached shards can exist without ever having been pinned), the union in step 4 is exactly the local shard alone. This reproduces the pre-shard-index rebuild's output byte-for-byte.

---

## Staleness guard (fail closed) — `check_shard_index_consistency`

**Enforced by:** `vault/tools/tropo-validate.py::check_shard_index_consistency`, read-only, via the shared `lib/shard_index.py::staleness_findings()` primitive (the SAME reachability/pin-match logic the writer's `resolve_shards()` uses — writer and validator cannot silently drift apart on the definition of "stale").

**A `vault_uid` pinned in `compose.lock` is CANNOT-COMPOSE when:**
- its shard cache (`.meta` and/or `.jsonl`) is missing entirely, or
- its `.meta` `resolved_commit` does not equal the current `compose.lock` pin (stale), or
- the `compose.lock` record itself is missing a `resolved_commit`.

**Severity: `[WARN]`, not `[ERROR]`** — a deliberate, disclosed judgment call. A stale/missing shard is a self-healing, local-only derived-cache condition: the very next `--apply` rebuild re-derives it automatically as long as `mount_path` is still reachable. It is not a governed-artifact trust-boundary breach (contrast `check_vault_manifest_governed_write_gate`'s `[ERROR]` for a hand-edited manifest) — it is closer in spirit to "a build cache needs a refresh." The fail-closed EXCLUSION (the shard's rows never enter `vault/00-index.jsonl` while cannot-compose) is itself the safe outcome this check exists to confirm is happening; the `[WARN]` tells an operator a mount has gone stale or unreachable so they can investigate, without implying the local studio's own governed content is at risk.

**`mount_path` reachability** follows the SAME advisory, LOCAL-MACHINE-state posture `compose-lockfile-schema.md` §`mount_path` already documents: unreachable means "cannot verify/re-derive this shard here," never a silent pass, and never a new hard-refusal surface — consistent with `check_vault_manifest_governed_write_gate`'s "cannot verify ≠ pass, cannot verify ≠ hard block" convention this schema explicitly follows.

**Zero real mounts today ⇒ `checked == 0`, `violations == 0`** — same "lands on a clean, verified base with no migration surface" posture the mount-gate and cross-vault member_of checks already established.

---

## Composition with `check_cross_vault_member_of` (4275b01c)

`check_cross_vault_member_of` reads the COMPOSED index's `segment` tags and excludes illegal (down-lattice) `member_of` edges. The shard-index change is entirely about HOW the union that produces `vault/00-index.jsonl` is assembled — it does not touch segment-tag assignment or the illegal-edge exclusion logic. Because segment tagging happens once, after the union, over the full record set (see "pre-segment-tag" note above), every record's segment tag is computed by the exact same `apply_gardener_pass` call `check_cross_vault_member_of` has always relied on — the shard-composed graph is indistinguishable, from that check's point of view, from a naive full-rescan's output. `test_cross_vault_member_of_4275b01c.py` is re-run unmodified as the regression proof for this compatibility contract.

---

## Example

```
.tropo-studio/shards/
  7c3a8e91.jsonl      # this vault_uid's cached index rows
  7c3a8e91.meta        # {"vault_uid":"7c3a8e91","resolved_commit":"a1b2c3d4e5f6...","derived_at":"2026-07-08T14:02:11Z","record_count":42}
```

```json
// 7c3a8e91.meta
{
  "vault_uid": "7c3a8e91",
  "resolved_commit": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
  "derived_at": "2026-07-08T14:02:11Z",
  "record_count": 42
}
```

---

## Rationale Summary

**Why cache pre-segment-tag rows, not post-tag rows:** segment discrimination is a function of the CURRENT rebuild's full composed view (ship-manifest membership can change as the local vault's own graph changes), not a static property of a single vault's content — freezing a `segment` value inside a shard would let it drift stale independently of the pin-diff mechanism this cache exists to make correct.

**Why `[WARN]` not `[ERROR]` for the staleness guard:** a self-healing local build-cache gap is a categorically different (and lesser) risk than a governed-artifact hand-edit; conflating the two severities would make the `[ERROR]` bucket noisier and less trustworthy as a "stop and look at this" signal.

**Why no independent hashing beyond the compose-lock pin:** the mount-gate's own dirty-check ([compose-lockfile-schema.md](compose-lockfile-schema.md) `resolved_commit` field) already guarantees `mount_path`'s working tree matches the pinned commit at mount time; a second hash of the same content the pin already vouches for would be redundant defense-in-depth with no additional real guarantee, at extra derivation cost.

---

## Refs

- **Dev-spec:** `vault/files/c6f6bea4.md` — Shard-keyed incremental composed index (ADR-051 Fork 4)
- **Test-spec:** `vault/files/ea352a6b.md`
- **ADR-051:** `vault/files/18059aef.md`
- **Compose-Lockfile Schema (the pin this cache keys on):** `.tropo/schema/compose-lockfile-schema.md`
- **Shared module:** `vault/tools/lib/shard_index.py`
- **Writer:** `vault/tools/tropo-rebuild-index.py`
- **Validator (staleness guard):** `vault/tools/tropo-validate.py::check_shard_index_consistency`

---

*Shard-Index Cache Schema v1 | Locked | Talos T26 | 2026-07-08*
*"Same lockfile ⇒ same shards ⇒ zero rebuild."*
