---
skill: tropo-mount-folder
name: tropo-mount-folder
type: how-to
purpose: Mount an ordinary folder from anywhere on the machine into the studio — searchable, governed, graph-linked — while it stays editable in its own app
when: Any time work lives in a folder outside the studio (Obsidian vault, OneDrive/SharePoint sync folder, a directory of documents) and you want agents to read, search and reason over it without moving or copying it
mode: inline
params:
  - path
  - name
uid: e392a8e6
status: active
owner: metis
created: 2026-08-02
created_by: metis-g99
governed_by: a5b3c891
capsule_version: '1.5'
extraction_scope: ship
schema_version: 2
trigger_description: 'Reach for this when content lives outside the studio and should be usable inside it. Mounting indexes a folder IN PLACE — no copy, no custody transfer. The source app keeps ownership of editing; the studio gets search, identity and graph edges.'
subsystem_hub:
  - 99ed55fd
tags:
  - mounting
  - external-folder
  - obsidian
  - composition
refs:
  - "5e6652ac"
  - "1e6a0b5d"
---

# tropo-mount-folder — bring an outside folder into the studio

**Proven on real work 2026-08-02**: Mike's MindBridge notes, 48 markdown files in `iCloud Drive/obsidian/mindbridge`, edited daily in Obsidian and fully usable from the studio. Mount `1e6a0b5d`.

## The model, in one line

**The file never moves and never gets copied.** The studio indexes it where it lives and holds a derived stub as a stable link target. The source app keeps editing.

## Two states, one switch

| State | What it means | What gets written into the folder |
|---|---|---|
| **attached** | Agents can read, search and change the files | **Nothing.** Verify with `find`, not the tool's message. |
| **adopted** | Same mount, tooled: sidecars per file, governed entries, folder structure projected as `project` containers | a `.tropo-studio/` sidecar directory |

## Do it

```bash
# 1. Attach — writes nothing into the folder
python3 vault/tools/tropo-folder.py --as <agent> mount "<absolute path>" --name <short-name>

# 2. Look. Confirm nothing was written.
find "<path>" -type f | wc -l     # compare to before

# 3. Adopt when you want it governed
python3 vault/tools/tropo-folder.py --as <agent> adopt <mount-uid>

# 4. After the folder moves, or files change outside the studio
python3 vault/tools/tropo-folder.py --as <agent> reconcile <mount-uid>

python3 vault/tools/tropo-folder.py --as <agent> list
python3 vault/tools/tropo-folder.py --as <agent> unmount <mount-uid>   # folder left exactly as it is
```

**Global flags precede the subcommand.** `--as <agent>` is recorded on the mount.

## Then search it

```bash
# content search — finds words INSIDE mounted files
python3 vault/tools/tropo-vault-search.py "<term>" --content
```

Mounted markdown is full-text indexed from the source, so `--content` finds a word that appears only inside a note. The cockpit's work-list filter searches the same index. *(Known gap: the cockpit's ⌘K global search uses a different engine and does NOT see mounted content — note `4af60d6e`.)*

## What you get

- **Search** over the real content, not the stub
- **Identity** — every file gets a UID, referenceable from any governed entry
- **Graph** — folders become `project` containers; `[[wikilinks]]` between mounted markdown files resolve to real edges. Mike's colleague notes produced 10 inbound edges to one team note on the first run.
- **Survives moves** — `reconcile` re-finds a moved folder by content anchor (verified at a 1.0 match after two moves)

## Rules that will bite you

**Edit at the source, never in the studio.** For a mounted text file the source is master; `vault/files/<uid>.md` is a derived, regenerable stub. The cockpit refuses to edit `external-artifact` for this reason. Hand-editing a stub does not stick — reconcile silently reverts it.

**Attach first, adopt second, with a look in between.** That is what the two states are for, not extra ceremony.

**Copy before you delete an original.** If you are relocating a folder into a mount, verify every file byte-identical (sha256, not counts) *before* removing the source. Git history is not a substitute for checking.

**`.obsidian/` and `.tropo-studio/` are excluded from adoption** by design — plugin config and sidecars are not content.

**Binaries get sidecars, not bodies.** A `.docx` or `.pptx` gets identity and provenance; its bytes are never indexed as text.

## For an Obsidian vault specifically

It is just a folder of markdown, so all of the above applies. Two extras worth knowing:

- Obsidian renders YAML frontmatter natively as **Properties**, so a mounted note can carry `type:`, `tags:`, `member_of:` and stay perfectly usable in the app.
- Keep binaries in one `attachments/` folder (Settings → Files & Links). Good Obsidian practice, and it gives the studio one predictable place where sidecars appear.

## Where the design lives

[5e6652ac](../files/5e6652ac.md) — the composition model: two mount kinds (folder / vault), publish is additive, `private` is the absence of a publish and never a permission.
