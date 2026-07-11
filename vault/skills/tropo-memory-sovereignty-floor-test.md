---
skill: tropo-memory-sovereignty-floor-test
name: tropo-memory-sovereignty-floor-test
type: how-to
purpose: 'The Memory Sovereignty floor test: prove an agent''s pin lands in Tropo memory (never .claude/), and that deleting the harness cache does not destroy the memory'
when: 'At Memory Sovereignty build close, or any time you want to verify the routing rule is working: write a pin → assert it''s in Tropo → delete the harness cache → confirm the pin survives'
mode: inline
params:
  - agent_slug
  - scope
uid: a5c4993d
status: active
owner: talos
created: 2026-07-03
created_by: talos-t24
governed_by: a5b3c891
capsule_version: '1.3'
extraction_scope: ship
schema_version: 2
trigger_description: 'The acceptance-criterion proof for dev-spec 8c015275: run this to prove memory sovereignty works. Seeds a test pin, invokes tropo-memory-write, confirms the pin is in Tropo (not .claude/), then executes the "delete-the-harness-cache plant" — deletes ~/.claude/ (or renames it) and confirms the pin is still readable. If the memory was written to .claude/ instead of Tropo, the delete kills it and the test fails.'
subsystem_hub:
  - 99ed55fd
tags:
  - memory-sovereignty
  - floor-test
  - portability-proof
  - 8c015275
  - acceptance-criterion
refs:
  - a5b3c891
  - 0b35633f
  - 8c015275
---

# tropo-memory-sovereignty-floor-test

**The Memory Sovereignty floor proof.** This test verifies that an agent's memory pin:
1. Lands in the correct Tropo tier (not `.claude/` or any harness-private store)
2. Survives deletion of the harness cache — proving portability by construction, not by assertion

If the memory write went to `.claude/` instead of Tropo, Step 5 destroys it. That is the test FAILING. The point is structural: Tropo memory is portable; harness memory is not.

---

## What passing proves

- Future agent memory writes route to portable Tropo memory by construction.
- An agent that uses `tropo-memory-write` (0b35633f) has a pin that survives harness cache deletion.

## What passing does NOT prove

- That historical `.claude/` pins were migrated (v3 work, explicitly deferred).
- That the discipline holds in a non-Claude harness without the cross-harness audit (v3 work, explicitly deferred).

---

## Pre-conditions

- `vault/skills/tropo-memory-write.md` (0b35633f) exists and is readable.
- The agent executing the test has write access to the target scope path.
- `~/.claude/` exists (or you know its equivalent for the harness under test).

---

## Steps

### Phase 1 — Baseline snapshot

1. **Record the current state of `~/.claude/`** (or harness-private equivalent). Run:

   ```bash
   ls -la ~/.claude/ 2>/dev/null && echo "CLAUDE_EXISTS" || echo "NO_CLAUDE_DIR"
   ```

   Note the file count / modification timestamps. This is the baseline. **If the directory doesn't exist, record that — a new pin must not create it.**

2. **Record the current state of the target Tropo memory path.** For scope=agent:

   ```bash
   ls agents/<agent_slug>/.tropo-capsule/memory/entries/ 2>/dev/null | wc -l
   ```

   Record the count.

### Phase 2 — Execute the memory write

3. **Invoke `tropo-memory-write` for a test pin.** Use scope=agent (or the scope under test). Follow the skill steps to:
   - Generate a test UID (e.g., `openssl rand -hex 4` → store as `TEST_UID`)
   - Write the entry file at `agents/<agent_slug>/.tropo-capsule/memory/entries/<TEST_UID>.md` with:

     ```yaml
     ---
     uid: <TEST_UID>
     type: memory
     subtype: semantic
     scope: agent
     context: "Memory Sovereignty floor test (a5c4993d) — verifying Tropo write routing"
     created: <today>
     state: active
     tags: [floor-test, memory-sovereignty, ephemeral]
     ---

     Floor-test pin. This entry exists to prove the memory-write routing rule works.
     Written by tropo-memory-sovereignty-floor-test (a5c4993d) per dev-spec 8c015275.
     If this file exists after ~/.claude/ is deleted, Tropo memory sovereignty is proven.
     ```

   - Append to the episodic log.

### Phase 3 — Verify Tropo landing

4. **Confirm the pin is in Tropo.** Assert:

   ```bash
   # Entry file exists at the correct Tropo path
   test -f "agents/<agent_slug>/.tropo-capsule/memory/entries/<TEST_UID>.md" && echo "PASS: in Tropo" || echo "FAIL: not in Tropo"

   # Tropo entry count increased by 1
   NEW_COUNT=$(ls agents/<agent_slug>/.tropo-capsule/memory/entries/ | wc -l)
   echo "Entry count: was <BASELINE_COUNT>, now $NEW_COUNT"
   ```

   **If the entry is NOT at the Tropo path → FAIL. Stop here. The routing rule is broken.**

5. **Confirm the pin is NOT in `.claude/`.** Assert:

   ```bash
   # Scan .claude/ for any file containing the TEST_UID
   grep -r "<TEST_UID>" ~/.claude/ 2>/dev/null && echo "FAIL: found in .claude/" || echo "PASS: not in .claude/"
   ```

   **If the test UID appears in `~/.claude/` → FAIL. The pin went to the wrong place.**

### Phase 4 — The delete-the-harness-cache plant

**Scope note:** Move ONLY the memory-store subdirectory (`~/.claude/projects/`), NOT the entire `~/.claude/` directory. Moving the entire `.claude/` dir from inside an active session running on that harness risks "sawing the branch" — the session itself may need the top-level directory to stay functional. The bounded form isolates the memory store (where project pins land) while leaving session infrastructure intact. This is the variant Argus A124 validated in test-leg 2cedb6a7.

**Out-of-session alternative:** If you want to move the entire `~/.claude/` as the original spec intended, run the test from an out-of-session context (e.g., a shell with no active Claude session). In that case, replace the step below with `mv ~/.claude ~/.claude-sovereignty-test-backup-$(date +%Y%m%d%H%M%S)` and adjust the restore step to match.

6. **Move (not delete permanently) the harness memory store to a safe backup location.** This simulates switching harnesses or losing harness-private state:

   ```bash
   # SAFE: rename, not delete — so you can restore after
   # Scoped: moves only the memory-store subdirectory, not the entire .claude/ dir
   mv ~/.claude/projects ~/.claude/projects-sovereignty-test-backup-$(date +%Y%m%d%H%M%S)
   echo "Moved ~/.claude/projects to backup"
   ```

   **After this step, `~/.claude/projects/` no longer exists.** Any pin that landed in the project memory store is now gone. The Tropo pin should survive because it was written to `agents/<slug>/.tropo-capsule/memory/`, not to `~/.claude/`.

7. **Confirm the Tropo pin still exists.** Assert:

   ```bash
   test -f "agents/<agent_slug>/.tropo-capsule/memory/entries/<TEST_UID>.md" && \
     echo "PASS: pin survives harness cache deletion — MEMORY SOVEREIGNTY PROVEN" || \
     echo "FAIL: pin is gone — it was written to harness-private storage, not Tropo"
   ```

   **This is the gate.** If `PASS`: the pin is in Tropo, portable, and harness-independent. If `FAIL`: the write routing rule did not work.

### Phase 5 — Restore and clean up

8. **Restore the harness memory store.** (You moved it, not deleted it.)

   ```bash
   # Find the backup
   BACKUP=$(ls -d ~/.claude/projects-sovereignty-test-backup-* 2>/dev/null | tail -1)
   if [ -n "$BACKUP" ]; then
     mv "$BACKUP" ~/.claude/projects
     echo "Restored ~/.claude/projects from $BACKUP"
   fi
   ```

9. **Clean up the test pin.** The floor test creates an ephemeral entry — remove it:

   ```bash
   # Remove the test entry from the entries/ directory
   python3 vault/tools/tropo-recycle.py <TEST_UID> --reason "Floor test cleanup — ephemeral test pin authored by a5c4993d"

   # Remove from episodic log: open the jsonl and delete the line with TEST_UID
   # (or leave it — the curator will handle it at next fold; it carries the 'floor-test' tag)
   ```

---

## Expected results (all must hold for PASS)

| Check | Expected |
|-------|---------|
| Entry exists at Tropo path after write | ✅ YES |
| Entry count at Tropo path increased by 1 | ✅ YES (+1) |
| Test UID appears in `~/.claude/` | ❌ NO (FAIL if yes) |
| Entry still exists at Tropo path AFTER `~/.claude/projects/` is moved away | ✅ YES |
| `~/.claude/projects/` successfully restored after test | ✅ YES |

---

## Interpreting failure

| Failure mode | Root cause | Fix |
|---|---|---|
| Entry not at Tropo path | `tropo-memory-write` wrote to wrong location | Check the scope→path mapping in the skill |
| Test UID found in `~/.claude/` | Agent wrote to harness store instead of calling the skill | CLAUDE.md + OP-14 routing rule not firing; check boot loading |
| Pin gone after harness cache move | Pin was in `.claude/` not Tropo | Same as above |
| `~/.claude/` restore failed | Backup path issue | Manual restore from backup |

---

## Relation to acceptance criteria (dev-spec 8c015275)

This test satisfies acceptance criterion #6: *"THE FLOOR TEST passes: an agent that invokes the abstraction lands the pin in Tropo memory (agent/studio/doctrine), and a scan of the harness-private store shows ZERO new substrate-class pins. The test FAILS if a substrate-class pin lands in .claude/."*

The "delete-the-harness-cache plant" is the structural proof: portability-by-construction, not portability-by-assertion.

---

*tropo-memory-sovereignty-floor-test | UID a5c4993d | Authored 2026-07-03 by Talos T24 | Dev-spec 8c015275 | acceptance-criterion proof for Memory Sovereignty v1.78.0*
