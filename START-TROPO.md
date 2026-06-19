---
extraction_scope: argo-reference
---

# Welcome to Tropo

**You're looking at a Tropo Studio — a way to run real work with AI agents using nothing but markdown files in this folder.**

To get started you need a folder-aware AI tool — one that can read and write files on your computer. The common ones: Claude Code, OpenAI Codex, Cursor, Windsurf. (Don't have one? Visit [tropo-ai.com](https://tropo-ai.com) for setup guidance.)

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

For engineers, architects, or anyone evaluating Tropo as infrastructure: read [the L1 canonical entry](vault/files/eca73d77.md) — what Tropo is, the typing system, the seven subsystems, the boot path. ~2,500 words; designed for the technically-curious. **Operators can skip this and come back later** — you don't need it to ship your first agent.

**The one-line frame engineers tend to trust:** *Markdown is the API.* Tropo's runtime is the LLM you're already running — no separate daemon, no SDK, no client library. The substrate is files; the contract is YAML frontmatter; standard Unix tools work. (Full answer in the Engineer FAQ below.)

For deeper technical questions:
- [How Capsules Work](vault/files/5f7a9d83.md) — the typing primitive
- [How Tropo Work Works](vault/files/2d4f8c91.md) — the work-management surface
- [Engineer FAQ](vault/files/8c4e1b73.md) — five technical questions answered
- [Enterprise FAQ](vault/files/b6a3f582.md) — governance, audit, compliance, multi-team scale

## What this is NOT for

- Pasting into a web chat (ChatGPT web, Claude.ai chat). The Studio needs filesystem access to work.

---

*Tropo-OS — see `.tropo/version.md` for the current version. tropo-ai.com.*
