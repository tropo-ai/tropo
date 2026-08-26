---
skill: tropo-first-dev-spec
name: tropo-first-dev-spec
type: how-to
purpose: Take a stranger from nothing to a closed dev-spec, unaided, using only what a shipped Studio contains — mint, lock, build, evidence, non-author verification, close
when: Your first dev cycle in a Studio you did not build. You have a Studio and something you want to build; you have no prior context and no human coaching you through it.
mode: walkthrough
params:
  - what-you-are-building
uid: ea724d2c
status: active
owner: talos
created: 2026-08-24
created_by: talos-t50
modified: 2026-08-24
modified_by: talos-t50
governed_by: 8dd772a0
capsule_version: '1.5'
extraction_scope: ship
schema_version: 2
trigger_description: 'The cold entry point for the dev-pipeline (cd1fcd25). Reach for this the first time you want to build something in a Studio and have never run its dev cycle before — it is the complete loop (mint -> author -> lock -> build -> evidence -> verify -> close) with copy-pasteable commands and no assumed context.'
subsystem_hub:
  - 76bab75f
tags:
  - dev-pipeline
  - stranger-studio
  - cold-entry-point
  - first-use
refs:
  - cd1fcd25
  - aeb2df3d
  - 41b7c9e2
  - 5187be30
  - 0b6b244c
---

# tropo-first-dev-spec — Your First Dev Cycle, Unaided

You have a Studio. You have something you want to build. You have never run this Studio's
dev cycle before, and nobody is here to walk you through it. This is the whole loop, start
to finish, with nothing assumed except that the Studio you are standing in shipped the tools
this page names.

**The shape:** mint → author acceptance criteria → lock → build → record evidence → get
non-author verification → close. Six moves. There is no seventh — closure happens as a side
effect of the last one passing, not as a step you run separately.

## Before you start

Pick ONE small thing to build. Your first cycle should be small enough that every command
below takes seconds, not because the loop can't handle more, but because your first walk
through any new mechanism should let you see the whole shape before you trust it with
something that matters.

## Step 1 — mint your dev-spec

```
python3 vault/tools/tropo-mint-id.py --type dev-spec --author <your-name>
```

This mints a complete governed dev-spec file from the registry's dev-spec template, writes
it, and prints the UID it was assigned. Note that UID — every command below takes it.

## Step 2 — author your acceptance criteria

Open the file the mint step just wrote (`vault/files/<uid>.md`) and fill in its
`acceptance_criteria:` frontmatter block. Each criterion needs an `id`, a `behavior` (plain
English — what must be true), and a `verify:` block naming a real command.

**The one rule that matters here:** every `verify.command` must be runnable EXACTLY as
written, by someone who is not you, with no placeholder left in it. Not `<run your test
here>` — the actual command. `python3 -m unittest tests.test_the_thing_you_built`, not a
description of what such a command would do. The lock in the next step refuses a dev-spec
with no acceptance criteria at all; it will not catch a criterion whose verify command is
prose pretending to be a shell line, so this discipline is yours to hold. A criterion nobody
else can run is a criterion nobody else can verify, which means it never actually closes —
it just looks closed.

`committed_substrate:` may stay empty for now — you haven't built anything yet, and a
dev-spec is locked *before* it's built. That's expected and the lock will not refuse it.

## Step 3 — lock it

```
python3 vault/tools/tropo-lock-dev-spec.py --dev-spec-uid <your-uid> --locked-by <your-name>
```

One gesture, and it does two things atomically: flips your dev-spec to `status: locked`,
and opens a correlated pipeline-activation — the run that will carry every step you take
from here forward. It prints the activation UID. Note that too; you'll need it for every
runtime command below.

If it refuses, nothing partial is left behind — your dev-spec file is byte-for-byte
unchanged. Read the refusal; it names exactly what's missing.

## Step 4 — build

Go build the thing. This step has no fixed shape — it's whatever your `committed_substrate`
and acceptance criteria actually require. When you're done, every target you named as
committed substrate should have a real, machine-readable artifact link (a file path, not a
claim that you built it).

## Step 5 — record evidence

There is no dedicated evidence-recording tool yet — until one ships, you append the row
yourself, directly to your run's journal. This is the exact, executable gesture; every field
is filled in, nothing here is a placeholder:

```
python3 - <<'PY'
import fcntl, json, os
from datetime import datetime, timezone

run_folder = "vault/pipeline-runs/<your-pipeline-run-folder>"  # printed by the lock step
path = f"{run_folder}/run.jsonl"

row = {
    "event": "ac_evidence_recorded",
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "actor": "<your-name>",
    "acceptance_criterion": "AC1",          # one row per criterion
    "dev_spec_uid": "<your-uid>",
    "verdict": "green",                      # or "red" if it isn't, yet
    "evidence_files": ["path/to/what/you/built"],
    "summary": "one or two sentences: what you verified, and how",
}

with open(path, "a") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
print("recorded")
PY
```

Run it once per acceptance criterion. The run's journal is the record — not your commit
message, not your memory of what you did. Anyone auditing this cycle later reads the
journal, not you.

## Step 6 — get non-author verification

Someone who did not build this re-runs every `verify.command` your acceptance criteria
name, verbatim, as written — not a command that looks similar, not the command re-typed
from memory. If you're working alone, this is the one step you genuinely cannot self-certify;
find a second pair of hands, even briefly.

## Step 7 — close

```
python3 vault/tools/tropo-close-dev.py --dev-spec-uid <your-uid> --actor <your-name> \
  --evidence <comma-separated-evidence-uids-if-you-have-them>
```

One command, ungated. It closes your dev-spec and archives the activation root. There is no
separate close *step* to run in the pipeline itself — closure happens as a side effect of a
passing terminal verdict, which is exactly why steps 5 and 6 matter: a close on evidence
nobody checked is a close on your own word, and this loop is built not to need that.

## When something refuses

Every refusal in this chain names what's wrong and changes nothing when it fires — a
refused lock leaves your dev-spec untouched; a refused close leaves your run open. Read the
message. It is written for a stranger, because it was designed for you.

## What you built

A complete, closed, verified dev cycle — with a run journal a stranger after you can read
cold, evidence a stranger after you can check, and a closure nobody had to take on faith.
