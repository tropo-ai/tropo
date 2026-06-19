# AGENTS.md — Standard Compatibility Note

*How Tropo's AGENTS.md relates to the Linux Foundation AGENTS.md standard.*

---

## Background

AGENTS.md is an open standard contributed to the Linux Foundation's Agentic AI Foundation (AAIF) in December 2025. Founding members include OpenAI, Anthropic, Google, and Block. The standard has been adopted by over 60,000 open-source repositories and is recognized by Claude Code, OpenAI Codex, Gemini CLI, Cursor, GitHub Copilot, Devin, and others.

## What the LF Standard Does

The LF AGENTS.md is a per-directory markdown file that gives AI coding agents project-specific context: build commands, test instructions, code style, PR conventions, security notes. Think of it as onboarding documentation for an AI teammate.

**Key properties:**
- Plain markdown, no required fields, no schema
- Supports per-directory placement (nearest file wins)
- Focuses on how-to-work-here instructions for coding assistants
- Says nothing about access control, ownership, or governance

## Where Tropo Aligns

Tropo uses the same filename (`AGENTS.md`), the same per-directory placement convention, and the same core intuition: put instructions where the agent will find them. Any platform that reads AGENTS.md will find Tropo's governance files and read them as valid markdown.

## Where Tropo Extends

Tropo adds structured governance on top of the LF convention:

| Layer | LF Standard | Tropo Extension |
|-------|------------|-----------------|
| **Format** | Free-form markdown | YAML frontmatter + markdown body |
| **Ownership** | Not addressed | `owner:` declares who maintains this folder |
| **Access control** | Not addressed | `write_access:` declares who can write here |
| **Folder semantics** | Not addressed | `folder_type:` classifies folder behavior |
| **Lifecycle** | Not addressed | `lifecycle:` declares permanence or time-boxing |
| **Validation** | Not addressed | Programmatic checks via vault validator |
| **Registry** | Not addressed | Integrates with UID-based file registry |

The YAML frontmatter is harmless to platforms that don't understand it — it renders as metadata text in any markdown viewer. This means Tropo's AGENTS.md files work on every platform that supports the LF standard, with richer behavior on platforms that parse the frontmatter.

## Compatibility Model

Tropo's AGENTS.md is a **superset** of the LF standard. A Tropo AGENTS.md file is a valid LF AGENTS.md file. The reverse is not true — an LF AGENTS.md without frontmatter is not governed in the Tropo sense, though it can coexist in a Tropo vault.

**On Codex:** Codex reads AGENTS.md natively at the root and per-directory. It will see Tropo's frontmatter as text and follow the markdown body instructions. Full compatibility.

**On Claude Code:** Claude Code reads CLAUDE.md as its root config. Tropo's CLAUDE.md tells Claude to also read AGENTS.md in every folder. Both files coexist — CLAUDE.md for Claude-specific boot, AGENTS.md for universal governance.

**On Cursor/Copilot:** Root configs (`.cursorrules`, `.github/copilot-instructions.md`) instruct the agent to read AGENTS.md in every folder. Governance travels via the same mechanism.

## The Novel Contribution

The LF standard tells agents **how to work**. Tropo's extension tells agents **who is allowed to write and under what rules**. These are complementary layers:

- LF: "Use kebab-case filenames, run tests before committing, follow this style guide"
- Tropo: "This folder is owned by the strategist. Only the strategist and the human owner can write here. New files need UIDs. Update the index when you create something."

Tropo is the first system to use per-directory markdown files for governance (access control, ownership, lifecycle) rather than just instructions. This is only possible because LLMs can reason about rules, not just follow steps.
