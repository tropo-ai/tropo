---
spec_version: 2
tier: capsule
folder_type: governed
owner: tropo
write_access: tropo
read_access: all
purpose: "Update-pipeline staging surface. Tropo-OS update packages land in pending/ for the Vault Steward to apply via the apply-update playbook. Read-only for all non-Tropo agents."
---

# system/updates/ — Tropo-OS Update Pipeline

This folder is the staging surface for Tropo-OS update packages. When a new Tropo-OS release is available for the user's Studio, the update package lands in `system/updates/pending/`.

## Files in this folder

- **`pending/`** — staging subfolder where waiting update packages are written. Created on first update arrival.
- **`applied/`** — archive of update packages that have been successfully applied (preserves audit trail). Created on first successful apply.
- **`logs/`** — apply-pipeline run logs. Created on first apply attempt.

## Update flow

1. Tropo writes an update package (per [update.capsule](../../../capsules/update.capsule.md) schema if applicable; or `.zip` archive) to `system/updates/pending/`.
2. Concierge boot protocol step 6 scans `system/updates/pending/` at every executive boot.
3. If a pending update exists, the concierge offers to apply via the [apply-update playbook](../../../playbooks/apply-update.playbook.md).
4. On successful apply, the package moves to `system/updates/applied/<YYYY-MM-DD>-<version>/`; apply-pipeline run log writes to `system/updates/logs/`.

## Write rules

- **Only Tropo writes here.** Agents do NOT manually drop files into pending/; updates arrive via the canonical Tropo update channel (GitHub release artifact, marketplace push, or equivalent).
- **Apply is opt-in.** The concierge surfaces the pending update + offers to apply; the principal decides whether to proceed.
- **Applied packages are preserved.** Don't delete from applied/; this is the audit trail of what's been applied to this Studio over time.

---

*system/updates/CAPSULE.md | Tropo-OS template | Folder-tier governance for the Studio's update-pipeline staging surface*
