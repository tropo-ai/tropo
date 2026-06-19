---
spec_version: 2
tier: capsule
folder_type: governed
owner: vault-admin
write_access: [human-owner, vault-admin-delegate]
read_access: all
purpose: "Reserved slot for binding contracts — future use. Cross-reference / integration bindings between this vault and external systems."
uid: e89818d0
status: reserved
---

# `.tropo-studio/bindings/` — Binding Contracts (Reserved)

## Purpose

**Reserved slot.** Ships empty in the skeleton. Reserved for future binding contracts — declarations about how this vault integrates with external systems: MCP servers, remote tools, cloud services, other vaults.

The concept exists in the three-tier architecture but no binding-type artifact has been formalized yet as of skeleton ship.

## What will likely belong here

(When the pattern formalizes, probably v1.3+)

- **MCP binding declarations** — named connection points to Model Context Protocol servers.
- **Remote vault bindings** — pointers to other Tropo-OS vaults if you're running a marketplace / federation.
- **External service credentials references** (paths to credential files; not the credentials themselves).
- **Integration contracts** — typed declarations about what a remote system provides to this vault.

## What does NOT belong here

- **Credentials or secrets** — use your OS credential store; reference by path.
- **Runtime state** — bindings are configuration, not state.
- **Kernel OS definitions** — those live in `.tropo/`.

## Current state

Empty. Leave the folder in place (the boot playbook may in the future declare it as a required slot). If you have binding-like needs before this slot formalizes, stash them in `directives/` with a `type: binding-draft` tag and a note.
