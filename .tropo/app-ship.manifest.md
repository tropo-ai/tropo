---
uid: ed10a8be
kind: app-ship-manifest
schema_version: 1
title: "App-Ship Publish Declaration — tropo-app subtree"
governed_by: f47da329
authored_by: argus-a135
authored_at: '2026-07-19'
segment_class: app-ship
default: deny
app_ship_prefix: tropo-app
pinned_commit_required: true
refused_git_modes:
  - "120000"   # symlink — may resolve outside the subtree
  - "160000"   # gitlink / submodule — ancestry + leak surface (F4)
deny_holes:
  # Governed deny-holes (F2): paths that fall UNDER app_ship_prefix but must
  # NEVER appear in a split. The gate refuses the publish if any match. These
  # are declared + reviewable here, not scattered as a code denylist.
  - "playbook-runs/**"
  - "pipeline-runs/**"
  - "vault/**"
  - "agents/**"
  - "channels/**"
  - "**/.tropo/**"
  - "**/.tropo-studio/**"
  - "**/.tropo-capsule/**"
  - "**/agent-memory.md"
  - "**/agent-memories.jsonl"
  - "**/*-activation.md"
  - "**/*.pem"
  - "**/*.key"
  - "**/*.p12"
  - "**/*.pfx"
  - "**/id_rsa*"
secret_allowlist:
  - ".env.example"
  - ".env.sample"
  - ".env.template"
secret_filename_patterns:
  # Secret-shaped basenames refused UNLESS the exact basename is in
  # secret_allowlist (F6). Restores the coverage the original gate's
  # SECRET_PATTERNS carried for real env/credential files — dropped when the
  # gate was grounded strictly in this manifest — while keeping the .env
  # templates shippable. Closes the .env.local / credentials leak
  # (Argus A135 ruling on Talos T34's flag). The .pem/.key/.p12/.pfx/id_rsa
  # shapes are already covered as deny_holes above; these add the env/cred set.
  - ".env"
  - ".env.*"
  - "credentials"
  - "credentials.*"
private_content_extensions:
  # Files with these extensions are content-scanned for private crew-data
  # markers before ship. Adds .jsonl / .ndjson (F5) — event streams and run
  # logs are the exact private-data shape the prior scan missed.
  - .md
  - .txt
  - .json
  - .jsonl
  - .ndjson
  - .ts
  - .tsx
  - .js
  - .py
  - .yml
  - .yaml
private_content_markers_hard:
  - "§Living-Transfer"
  - "Living-Transfer-from-Predecessor"
  - "§Top-of-Mind"
  - '"event": "run_created"'
  - '"type": "tropo.broadcast.crew"'
  - '"type":"tropo.broadcast.crew"'
  - '"party_uid"'
  - '"agent_root_uid"'
---

# App-Ship Publish Declaration

*Governed studio-tier declaration that lives ABOVE the `tropo-app/` subtree, in `.tropo/` (the private studio governance layer — never inside the shipped subtree, so it is un-forgeable from within `tropo-app/`). It confers the `app-ship` segment TOP-DOWN (Argus A128/A134 ruling): a non-vault mounted directory has no frontmatter / UID / vault-manifest of its own, so its shippability is authorized here, not asserted from inside it.*

## Contract

This declaration is the **F1 grounding** for [`vault/tools/tropo-publish-scope-gate.py`](../vault/tools/tropo-publish-scope-gate.py). The gate reads it and derives its rules from it rather than from a hardcoded, floating denylist (a floating-HEAD denylist is convenience, and convenience is not isolation).

- **Default-deny (studio level).** Nothing ships unless it is declared shippable. The only declared-shippable scope is `app_ship_prefix` (`tropo-app/`); `git subtree split --prefix` enforces that boundary by construction. Within the prefix, `deny_holes` are refused and `private_content_extensions` are content-scanned.
- **Governed deny-holes (F2).** `deny_holes` names paths under the prefix that must never ship even though they are under `tropo-app/`. This is where the latent `tropo-app/playbook-runs/agent-retire-argus-a59-.../run.jsonl` leak is closed — as a governed hole, reviewable in this manifest, not a convenience patch.
- **Pinned commit (F3).** `pinned_commit_required: true` — the gate splits + verifies against a PINNED source commit supplied by the changeset, never a floating `HEAD`. The split file set is cross-checked against `tropo-app/` **at that pinned commit**.
- **Refused git modes (F4).** `refused_git_modes` — symlinks (`120000`, may escape the subtree) and gitlinks/submodules (`160000`, an ancestry + leak surface) in the split are refused.
- **Content scan (F5).** Files whose extension is in `private_content_extensions` (now including `.jsonl` / `.ndjson`) are scanned for `private_content_markers_hard`; a match is a hard refusal.
- **Secret filenames (F6).** A split path whose basename matches a `secret_filename_patterns` glob is refused **unless** the exact basename is in `secret_allowlist`. This is allowlist-exempt (unlike `deny_holes`, which are unconditional), so real secret files (`.env.local`, `.env.production`, `credentials`) are refused while the `.env.example` / `.env.sample` / `.env.template` templates still ship. It restores the coverage the original hardcoded `SECRET_PATTERNS` carried before the gate was grounded in this manifest.

## Boundary separation (do not merge code paths)

This is the **app-subtree split** authorization path. It deliberately does NOT share a code path with the **vault-record federation** boundary (`44badb55` / [`vault/tools/lib/segment.py`](../vault/tools/lib/segment.py)), which authorizes governed markdown vault entries by `extraction_scope` + derived vault-node segment. The two paths authorize different classes of thing and must stay separate (Argus A134 ruling). This manifest governs only the app-ship class.

## Authority

Signing the scope gate against this declaration is an irreversible outward-facing act and requires Mike's explicit GO (Argus does not self-authorize the cut). This manifest makes the boundary reviewable; it does not itself authorize a publish.

---

*App-Ship Publish Declaration | UID `ed10a8be` | Argus A135 2026-07-19 | governed by dev-spec `f47da329` | the F1 grounding for `tropo-publish-scope-gate.py`.*
