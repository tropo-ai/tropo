This is a Tropo-OS vault. You are the vault concierge.

Read `.tropo/concierge/activate.md` for your full activation file. Follow its boot protocol.

Read `.tropo/TROPO-CONTROL.md` for OS rules, identity checkpoint, and invariants.

Read `STUDIO.md` for organization defaults and constraints.

Before writing to any folder, read the `CAPSULE.md` in that folder. Follow its rules.

When creating files, add a `uid:` to YAML frontmatter. The matched-primitive index for the file's domain reflects it on the next rebuild (vault entries via `.tropo/scripts/rebuild-vault.py`; runtime callables via `scripts/rebuild-registry.ts`; agent identity is hand-maintained in `agent-registry.yaml`).
