# Welcome to Tropo

**You're looking at a Tropo Studio — a way to run real work with AI agents using nothing but markdown files in this folder.**

To get started you need a folder-aware AI tool — one that can read and write files on your computer. The common ones: Claude Code, OpenAI Codex, Cursor, Windsurf. (Don't have one? Visit [tropo-ai.com](https://tropo-ai.com) for setup guidance.)

## Compacted session? Continue — do not activate

> If this agent session was compacted or you no longer remember completing boot, do not activate and never run `born`. Run `python3 vault/tools/tropo-compact-continue.py --agent <slug>` before any other work.

Continue means this same agent session keeps going. Nothing is born, retired, or added to
permanent lineage. Compaction is not retirement: an imminent auto-compact warning routes here,
not to the retirement playbook.

## First setup after unzip

There is nothing to run by hand. Open your AI tool in the extracted Studio folder and say hello:
**Po, the concierge, sets the Studio up at her first greeting** — she builds your local index and
navigation and mints this Studio's own identity, on your machine, in about a minute. *(Until v1.95
this section told you to run `tropo-rebuild-index.py` yourself before opening anything; Po runs it
now — v1.95 Spine A, Mike-ruled 2026-09-05.)*

Release packages omit machine-local derived indexes and carry no Studio identity, so the same zip
is portable across macOS, Linux and Windows, and two people who unzip it become two different
Studios. Po derives your local index and navigation from the shipped source files and mints this
Studio's identity (`.tropo/studio-identity.md`) on your machine. Normal first-time setup, not a
repair — and hers to run, not yours.

**If you watch her do it, expect a large block of `[WARN] mentions parser: dead link to <uid>`
lines — roughly 1,200 on a fresh box.** Nothing is wrong. Those warnings report prose mentions of
Tropo's own internal UIDs that were not part of the shipped set; they are informational and the
index is written correctly. A successful run ends with `Wrote vault/00-index.jsonl`, `Wrote
vault/00-index.sqlite`, `Wrote vault/00-project-tree.jsonl`, `✓ rehydrate.py succeeded` and
`✓ mint registry generated`. If Po reports those, setup worked.

## Checking your Studio's health (optional)

If you want to confirm the Studio is structurally sound, run the validator **with `--customer`**:

```bash
python3 vault/tools/tropo-validate.py --customer
```

**Always pass `--customer`.** The flagless form additionally runs vendor-development checks that
do not apply to your Studio — it treats Tropo's own internal cross-references, which by design
were never shipped to you, as failures. On a pristine box the flagless form reports failures
and `--customer` reports 0; both are looking at the same, healthy Studio. Genuine problems inside
your box still fail loudly under `--customer`, so nothing real is hidden.

Run this only after the index rebuild above. Before the index exists there is nothing to validate
against, and the validator will report failures for that reason alone.

## How to activate (under a minute)

1. **Open your AI tool with this folder as its working directory:**
   - **Claude Code:** open a terminal in this folder, type `claude`, press enter. The Studio auto-activates from `CLAUDE.md`.
   - **Cursor / Windsurf:** open this folder as the project root, then ask the AI: *"please read CLAUDE.md and activate the Tropo Studio."*
   - **Codex / Gemini CLI:** open a session in this folder, then ask the AI: *"please read START-TROPO.md and activate the Tropo Studio."*
2. **Wait for the AI to greet you.** The first message should be the Tropo concierge offering to help.

## Want to skip ahead and just make your first agent? (5 minutes)

Once the concierge greets you, say: **"I want to create my first agent."** The AI routes you to the [create-an-agent playbook](.tropo/playbooks/concierge-paths/create-an-agent.playbook.md), asks ~3 questions about what you want the agent to do, and ships a working agent in your Studio in about 5 minutes. No deep reading required — your AI does the configuration. You drive.

**Stuck?** Read the [operator FAQ](vault/files/4e7d2c91.md) — plain-English answers to the five questions first-time users most often ask.

## Want the technical overview first?

For engineers, architects, or anyone evaluating Tropo as infrastructure: read [the L1 canonical entry](vault/files/eca73d77.md) — what Tropo is, the typing system, the nine subsystems, the boot path. ~2,500 words; designed for the technically-curious. **Operators can skip this and come back later** — you don't need it to ship your first agent.

**The one-line frame engineers tend to trust:** *Markdown is the API.* Tropo's runtime is the LLM you're already running — no separate daemon, no SDK, no client library. The substrate is files; the contract is YAML frontmatter; standard Unix tools work. (Full answer in the Engineer FAQ below.)

For deeper technical questions:
- [How Capsules Work](vault/files/5f7a9d83.md) — the typing primitive
- [How Tropo Work Works](vault/files/2d4f8c91.md) — the work-management surface
- [Engineer FAQ](vault/files/8c4e1b73.md) — five technical questions answered
- [Enterprise FAQ](vault/files/b6a3f582.md) — governance, audit, compliance, multi-team scale

## Two files in this folder that are ours, not yours

Two files at the Studio root are build records from the release that produced this package,
not part of your own work. You do not need to read either one to use your Studio. Leave them in
place — Tropo's own tooling refers to them.

- **`MANIFEST.md`** — the packing slip: every file we shipped, with a fingerprint for each. This
  is what the update guarantee in `README.md` refers to when it says an update may only touch
  files on that list.
- **`test-report.md`** — the result of the mechanical release checks that ran against this package
  before it shipped. It describes *our* build, not the health of *your* Studio. For your Studio,
  run the validator above.

## What this is NOT for

- Pasting into a web chat (ChatGPT web, Claude.ai chat). The Studio needs filesystem access to work.

---

*Tropo-OS — see `.tropo/version.md` for the current version. tropo-ai.com.*
