# Template/Instance Pattern — Tropo-OS Convention

How governed artifacts are defined once and used many times.

---

## The Pattern

Every governed artifact in Tropo follows the same three-part pattern:

### 1. Template (in `.tropo/`)

The **definition**. What this type of artifact looks like, what fields it requires, what behavior it expects. Templates live in the kernel and are maintained by the framework.

| Artifact | Template Location |
|----------|------------------|
| Executive agent — activation | `.tropo/templates/executive-activation.template.md` |
| Executive agent — charter | `.tropo/templates/executive-charter.template.md` |
| Executive agent — briefing | `.tropo/templates/executive-briefing.template.md` |
| Task agent | `.tropo/templates/task.template.md` |
| System agent | `.tropo/system/[name].template.md` |
| Playbook | `.tropo/playbooks/` (framework playbooks serve as reference templates) |

### 2. Instance (in user space)

The **actual artifact**. Created from the template, customized for its purpose, lives in its designated folder.

| Artifact | Instance Location |
|----------|-------------------|
| Executive agent — activation | `agents/[name]/[name]-activation.md` |
| Executive agent — charter | `agents/[name]/[name]-charter.md` |
| Executive agent — briefing | `agents/[name]/[name]-briefing.md` |
| Task agent | `agents/[parent]/tasks/[task-id].md` |
| System agent | `system/[name]/activate.md` |
| User playbook | `playbooks/[slug].playbook.md` |

### 3. Phone Home

Instances **read their template at boot**. When the kernel updates (new template version, new protocol, new capabilities), instances pick it up at their next activation. This is how the framework upgrades without touching user files.

**How it works:**
- The agent's boot sequence includes reading the template from `.tropo/`
- The template declares the current expected structure and protocols
- The instance follows the template's protocols while keeping its own identity and content
- If the template adds a new section the instance doesn't have, the agent adapts

**What this means for upgrades:**
- Framework updates modify files in `.tropo/` only
- User-created files in `agents/`, `playbooks/`, `system/` are never touched by upgrades
- Instances inherit new behavior at their next activation — no migration scripts needed

---

## When to Use This Pattern

Use template/instance when creating:
- A new agent (read the template, generate an instance with the founder's content)
- A new system agent (copy the template to an instance folder, customize)
- A new playbook (reference the framework playbooks for format, create in `playbooks/`)

Do NOT use template/instance for:
- User content files (documents, research, notes) — these don't need templates
- Configuration files (operating agreement, registry) — these are singular, not instanced
- Indexes and AGENTS.md — these are structural, not templated

---

## The Sidecar Pattern (for non-markdown files)

When a user brings in files that aren't markdown (Word docs, spreadsheets, images, PDFs), they live in the flexible space as-is. The governed core describes them through:

1. **Index rows** — the `00-index.md` in the folder lists the file with metadata (type, description, owner)
2. **Sidecar files** (optional) — for files needing richer description, create `[filename].meta.md` alongside the binary file

Example:
```
projects/q3-rebrand/
 00-index.md <- describes all files including non-markdown
 brand-guidelines.pdf
 brand-guidelines.pdf.meta.md <- optional: extended metadata, tags, relationships
 logo-final.png
 campaign-plan.md
```

The sidecar file contains:
```yaml
---
describes: "brand-guidelines.pdf"
type: PDF
pages: 24
owner: marketing-team
tags: [brand, guidelines, q3]
---

Brand guidelines document covering logo usage, color palette, typography, and tone of voice.
Updated quarterly. Current version covers the Q3 rebrand initiative.
```

The agent's LLM handles actually reading the binary file. Tropo just makes sure agents know it exists and what it's for.
