# Vault Memory Index

*The shared memory of this vault's crew. All agents read this index at boot.*
*Individual files in this folder. Keep under 200 lines.*

---

## Shipped with Tropo-OS (preserved across vault setup)

- [Deletion Discipline — Never destroy governed substrate; always soft-delete](839a65f9.md) — every agent reaches for `tropo-recycle.py` by reflex; never `rm` (v1.40.0 doctrine)

*Add your own memories below. Format: `- [title](filename.md) — one-line description`*

*Early candidates for the first few entries: the human's preferred response style, naming conventions locked for this vault, organizational decisions that every agent should know at boot, tools the crew has settled on.*

---

## Adding a memory

Append one line to the list above once you have memories: `- [title](filename.md) — one-line description`

Format: plain markdown, minimal YAML frontmatter (`name`, `description`, `type`, `created`, `created_by`). See the [CAPSULE.md](CAPSULE.md) in this folder for the format and what belongs here.

**What goes here:** Cross-agent patterns. Human preferences that apply to everyone. Organizational decisions. Anything whose audience is "every agent in the vault" rather than "future generations of one specific agent."

**What does NOT go here:** Agent-specific operational knowledge (that goes in `agents/<name>/.tropo-capsule/memory/`). Temporary session context. Historical narrative (transfers, reflections).

---

*Vault-Level Memory Index | Shipped empty with Tropo-OS skeleton*
