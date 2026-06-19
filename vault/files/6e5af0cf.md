---
uid: 6e5af0cf
type: kb-article
title: Working with Existing Files
description: Your files don't change. The vault understands them.
status: published
state: active
author: argus-a55
created: 2026-05-11
created_by: argus-a55
modified: 2026-05-11
modified_by: argus-a56
schema_version: 2
governed_by: 4cb20382
extraction_scope: ship
member_of: []
subsystem_hub:
- 2d083137
- f87e33f0
capsule_version: '2.5'
---

# Working with Existing Files

**Relations**

| Relation | Target |
|---|---|
| Governed by | [kb-article (4cb20382)](4cb20382.md) |

*Your files don't change. The vault understands them.*

## The Short Version

Tropo doesn't require you to convert anything to markdown. Your Word docs, spreadsheets, PowerPoints, PDFs, images, code files — they all live in your vault exactly as they are. Tropo's job is to make sure your agents know they exist and what they're for.

## How It Works

When you bring existing files into your vault, three things happen:

1. **The index describes them.** Every folder has a `00-index.md` that lists what's in it. When agents add your files to the index, they record the file name, type, and a short description. This is how agents find things.

2. **The governance wraps around them.** The folder's `AGENTS.md` file sets rules — who can read these files, who can modify them, what conventions to follow. Your files get the same governance as everything else in the vault.

3. **Your AI reads them natively.** Modern AI tools (Claude Code, Codex, Cursor, Gemini) can read most common file types — PDFs, images, code, and often Office documents. Tropo tells the agent what exists. The AI handles actually reading it.

## What You Can Bring In

| File Type | How Agents Use It |
|-----------|-------------------|
| **Markdown** (.md) | Full native support. Agents read, write, and govern these directly. |
| **Documents** (.docx,.pdf,.txt) | Agents read content using their AI's capabilities. Indexed by the vault. |
| **Spreadsheets** (.xlsx,.csv) | Agents can read data and reference it in their work. CSV is easiest. |
| **Presentations** (.pptx) | Agents can describe content. Best paired with an index description. |
| **Images** (.png,.jpg,.svg) | Multimodal AI can view these. Indexed with description. |
| **Code** (.py,.js,.ts, etc.) | Full native support. Agents read and understand code directly. |

## How to Add Existing Files

**Option 1: During onboarding.** When the concierge asks "Do you have existing project files?", point it to a folder. The agent will scan, index, and add governance automatically.

**Option 2: Anytime after setup.** Tell any agent: "I want to add my Q2 project files to the vault." The agent will:
1. Scan the folder you point to
2. Create a `00-index.md` listing every file with type and description
3. Create an `AGENTS.md` with appropriate governance
4. Confirm the index with you before finalizing

**Option 3: You create the folder yourself.** If you drop a folder directly into the filesystem and tell the agent about it, the agent MUST still create the folder's `AGENTS.md` and `00-index.md` — the same rules apply whether the folder arrived through the concierge or through Finder. If you notice the agent registered your files but did not create folder-level governance, ask it: "Did you add an AGENTS.md and 00-index.md to that folder?" — this is part of its Working Protocol.

**Your files don't move.** They stay wherever you put them. The vault just indexes and governs the folder they're in.

## Two Layers of Tracking

When a folder of files is brought into the vault, two things happen:

1. **Domain-matched discovery primitives** — every governed markdown file carries a UID, indexed in the appropriate primitive for its domain: vault entries project into `vault/00-index.jsonl` via the rebuilder; agent identity records live in `.tropo-studio/registries/agent-registry.yaml`; runtime callables (sa.\*/skills/tools) project into `.tropo-studio/registries/registry.jsonl`; capsules / kernel playbooks / kernel skills are discoverable via folder listing. Non-markdown files (Word, PDF, images) are NOT given UIDs at this layer — they're described in folder indexes only.

2. **Folder-level governance** — the folder itself gets an `AGENTS.md` (who can write here, what belongs) and a `00-index.md` (what's inside). This is local context. Every file in the folder is listed in the index, including non-markdown files.

Both layers are required. Registry without folder governance means agents don't know what a folder is for. Folder governance without registry means files aren't cross-referenceable across the vault. Agents that skip either layer are not following the Working Protocol.

## When Files Need More Description

Most files are fine with an index row — name, type, one-line description. But sometimes a file needs richer context: tags, relationships to other files, detailed description, version history.

For those cases, create a companion file: `[filename].meta.md`. For example, `brand-guidelines.pdf` gets a `brand-guidelines.pdf.meta.md` with extended metadata. The index references both.

This is optional. Start with index rows. Add sidecars when you need them.

## What Tropo Does NOT Do

- **Convert files.** Your PowerPoint stays a PowerPoint. Tropo doesn't turn it into markdown.
- **Parse binary content.** Tropo describes files through indexes. Your AI tool handles the actual reading.
- **Replace your file organization.** You choose where files go. Tropo adds governance and discoverability on top.
