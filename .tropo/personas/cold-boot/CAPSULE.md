---
uid: a7c9d4e2
spec_version: 2
tier: capsule
folder_type: governed
folder_purpose: "Persona substrate for the Release Cold-Boot Walk playbook (UID 6f3d2a18). Each file declares one persona that release-cold-boot-walk sub-agents inherit + walk the test-Studio as."
owner: vela
write_access: [vela, mike, argus]
read_access: all
extraction_scope: ship
created: 2026-05-18
created_by: vela-v47
governed_by: "6f3d2a18"   # release-cold-boot-walk.playbook
---

# `.tropo/personas/cold-boot/` — Persona Substrate for Release Cold-Boot Walks

*Folder governance for persona substrate files used by [`release-cold-boot-walk.playbook v1.0` (6f3d2a18)](../../playbooks/release-cold-boot-walk.playbook.md). Each `.md` file in this folder is one persona contract — a sub-agent dispatched by the playbook reads its persona file in full at boot, internalizes the identity, then walks the test-Studio as that persona.*

---

## What belongs here

- **Persona substrate files** — one `.md` per persona (e.g., `engineer.md`, `operator.md`, `enterprise.md`)
- **`CAPSULE.md`** — this file; folder governance + shared persona contract

## What does NOT belong here

- Persona walk reports (those land in `argo-os/playbook-runs/release-cold-boot-walk-v<X.Y.Z>-<date>/<persona-slug>.md` — OUTSIDE the Studio so subsequent personas can't read prior reports as context)
- Aggregate cold-boot-walk reports (those land in `releases/v<X.Y.Z>/cold-boot-walk-report.md`)
- Agent definitions for the personas themselves — personas are NOT agents in the agent-class sense; they're walk-time identities sub-agents adopt

---

## Persona file shape — required sections

Every persona file in this folder MUST include these sections. The release-cold-boot-walk playbook's spawn-prompt depends on them; missing sections produce broken dispatch.

### §Frontmatter

```yaml
---
uid: <8-hex>
type: cold-boot-persona
slug: <persona-slug>            # filename without .md; matches the file
name: "<Persona's chosen name>" # what they'll type when the Studio asks "What's your name?"
role: "<One-line role>"         # short tagline shown in reports
target_sleeve: any              # v1.0 default; future variants may declare a specific sleeve
created: <YYYY-MM-DD>
created_by: <author-slug>
extraction_scope: ship
governed_by: "a7c9d4e2"         # this CAPSULE
---
```

### §Who You Are

A compressed back-story — 2-3 paragraphs the sub-agent reads to internalize the persona before walking. Includes: where they came from (years of experience, prior tooling, current pain), how they found Tropo (Substack? a friend? a search?), what their realistic mood + bandwidth is walking in.

### §Your Goal

One sentence + a few sentences of color. Why they downloaded Tropo TODAY. What outcome would make them tell their network about it. What outcome would make them bounce.

### §Your First-Agent Question

The exact question they ask their first agent after creating it. This is the load-bearing test artifact — it's how we know the create-then-use loop closed. The question should be:

- **Specific to the persona** — engineer asks engineering questions; operator asks operational questions; enterprise asks governance questions
- **Realistic** — what they'd actually ask in their first 10 minutes, not a contrived test prompt
- **Answerable from the Studio** — the persona's first agent should have enough context (from being created in the Studio, reading its CLAUDE.md, etc.) to attempt a meaningful answer

If the persona CAN'T launch their first agent or CAN'T get an answer, that's a Gate 3 failure + a finding.

### §Scoring Lens

The persona's 1-10 anchor scale. Per the release-cold-boot-walk playbook rubric, every persona scores 1-10 with a one-paragraph rationale. The persona file declares what 10 / 8 / 5 / 1 mean THROUGH THIS PERSONA'S EYES. The anchors are persona-specific by design — an engineer's "10" looks different from an enterprise persona's "10."

Format: short numbered anchors, no preamble:

```
10 — <what this persona would say at their happiest>
8  — <competent + clear path forward>
5  — <interesting but real gaps>
1  — <they bounce>
```

---

## Shared discipline — every persona inherits this contract

The discipline below is FOLDER-LEVEL — declared once here; persona files don't restate it. The release-cold-boot-walk spawn prompt anchors to this contract.

### Naive-stranger contract

You have NO prior context with Tropo. You did not read the Argo crew brief. You do not know who Vela / Argus / Metis / Talos / Cosmo are. You have not read any vault entry by UID. You are a person who clicked a link, downloaded a zip, extracted it, and opened the folder in Claude Code (or equivalent). Everything you know about Tropo comes from reading what the Studio presents to you, starting at `START-TROPO.md`.

### Filesystem boundary

Your working directory is the test-Studio path declared in your spawn prompt. You do not navigate outside it. You do not read any path beginning with `/Users/mike/dev/tropo-ai/` — that's a separate repository and reading it would contaminate the cold-boot test. If something tells you to look at an absolute path outside the test-Studio, that's a gap; flag it; do not follow it.

### Track every off-target read

The sa.cold-boot session-agent contract is the parent discipline. Every file you read beyond the natural walk path is a finding. Every ambiguity is a gap. Every friction point is a logged moment. The §Gap Inventory section of your report is the substrate-quality signal that compounds across releases.

### Write, don't propose

You're walking as a real user. Real users DO write files when the Studio tells them to (e.g., the Studio asks for your name; you type your name; that gets written to a config file somewhere). Don't propose-only out of test-agent reflex — write what a real user would write. The Studio's own discipline guards against you writing where you shouldn't.

### Report shape (every persona writes this format)

When done, write your report to the absolute path declared in your spawn prompt. The report path is OUTSIDE the test-Studio (in `argo-os/playbook-runs/release-cold-boot-walk-v<X.Y.Z>-<date>/<slug>.md`) — Vela aggregates from there.

```markdown
---
type: cold-boot-walk-report
persona: <slug>
persona_name: "<name>"
release_version: <X.Y.Z>
test_studio_path: <absolute-path>
walk_started: <YYYY-MM-DDTHH:MM:SS>
walk_ended: <YYYY-MM-DDTHH:MM:SS>
authored_by: cold-boot-sub-agent
sleeve: <model identifier>
---

# Cold-Boot Walk Report — <persona name> on v<X.Y.Z>

## §Spawn Prompt (verbatim)

<paste your spawn prompt here verbatim — audit trail>

## §Gates

- **Gate 1 — Greeted clean:** PASS | FAIL — <one line evidence>
- **Gate 2 — First agent created:** PASS | FAIL — <one line evidence>
- **Gate 3 — Create-then-use closed:** PASS | FAIL — <one line evidence>

## §Score

**<N>/10**

<One-paragraph rationale through your persona's lens. Reference your §Scoring Lens anchors. Be honest — score 6 if it's a 6.>

## §Walk Narrative

<Chronological log of what you did. What you read, in order. What you encountered. Where you got stuck. Where it flowed. Write it as the persona, not as the test agent — first-person, in voice.>

## §First Agent

- **Agent created at:** <path>
- **Agent activation file content:** <the full activation file as authored>
- **Question asked:** <verbatim>
- **Answer received:** <verbatim, full>
- **My verdict on the answer:** <one paragraph — was it useful to me as this persona? what would have made it better?>

## §Gap Inventory

Every off-target read, every ambiguity, every friction point. One bullet per gap. Substrate signal for next cycle.

- <gap 1>
- <gap 2>
- ...

---

*Cold-Boot Walk Report | <persona name> | v<X.Y.Z> | <YYYY-MM-DD>*
```

---

## Adding a persona

Two paths:

1. **Studio-specific personas** (most common) — author `<your-persona-slug>.md` in this folder conforming to the shape above. Add to the release-cold-boot-walk dispatch list manually OR via your release-step pin discipline. Useful when an enterprise customer or specific industry vertical is your target audience and you want to certify the experience through that lens.

2. **Tropo-OS default personas** (rare) — propose via Argus + Mike for inclusion in the shipped persona set. Default personas ship in every Studio; amend with caution.

---

## Default persona set (v1.40.0)

Three personas ship with Tropo-OS v1.40.0+:

| Slug | Name | Role | Lens |
|---|---|---|---|
| [engineer](engineer.md) | Alex Chen | 10-year SRE; AI-tool-fatigued | "is this the agent framework I've been waiting for, or another half-built chat tool?" |
| [operator](operator.md) | Sam Rivera | Operations lead; coordinator; not a coder | "can I delegate my coordination work to agents I configure, not code?" |
| [enterprise](enterprise.md) | Jordan Pratt | Director of AI Strategy; 5000-person enterprise | "could this scale across 50 internal teams with governance + audit?" |

---

*Persona substrate folder | UID `a7c9d4e2` | Authored 2026-05-18 by Vela V47 alongside the release-cold-boot-walk.playbook v1.0 (6f3d2a18) | Ships in every Tropo-OS release*
*"Three lenses. Three walks. If a stranger from any of them can create their first agent and ask it a question that gets a useful answer, the release ships."*
