---
canonical_substrate_uid: "166c07db"
migrated_from: ".tropo/playbooks/apply-update.playbook.md"
migrated_at: "2026-06-11"
migrated_by: talos-t15
status: active
repointed_at: '2026-09-06'
repointed_by: orpheus-o38
repoint_note: "v1.95 AC7 content cure (Metis G122 slice, Mike: cure first). The v1.69 canonical this pointer named, 71f186cf Apply a Tropo-OS Update, was superseded on 2026-08-21 by the v1.90 lift-and-replace update engine (dev-spec ea09fc6e, argo history, not shipped) and is excluded from the box by declaration; the shipped procedure for applying an update is the Update Walk below."
---

# Apply a Tropo-OS Update — Thin Pointer

*Canonical substrate: [`vault/playbooks/166c07db.md`](../../vault/playbooks/166c07db.md) — **Update Walk, Box Flow**: download the release image to a staging folder outside the studio, then `tropo-apply-image.py plan`, read the plan, then `apply` (a full backup is taken first). This file is a thin pointer; all content is at the canonical path.*

*History, in words: the v1.69 playbook-unification pointer named "Apply a Tropo-OS Update" (uid 71f186cf), superseded at v1.90 when the update engine became plan-then-apply with an honest progress bar; that older playbook stays in the authoring studio as history and does not ship. Repointed 2026-09-06 by Orpheus O38 under the v1.95 doc-currency cure.*
