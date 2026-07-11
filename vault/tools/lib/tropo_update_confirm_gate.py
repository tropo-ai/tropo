"""The confirm hard-stop — a structural per-item acknowledgment gate (Gate 2,
dev-spec fc4874f4, LOCK-AMENDMENT 3, 2026-07-02). Findings record: 5d4bbbf2,
finding F1-confirm.

THE FINDING THIS CODE FIXES: in the Po walk, the concierge (Po's boot path)
bypassed two per-file overwrite-confirms — `.tropo-studio/registries/
subsystem-registry.jsonl` and the root `MANIFEST.md` — by reasoning that the
user's blanket "go ahead and apply" approval covered them ("redundant
per-file prompt"). The outcome was harmless (both files were OS-shipped
substrate, not user content), but the behavior CLASS is exactly what the
covenant forbids: an agent judgment-call folding a designed per-item stop
into a broader approval it was never scoped to cover.

The fix is not "tell the agent not to do that" (prose an agent can read past
under time pressure or its own plausible-sounding reasoning — which is
precisely what happened). The fix is structural: `ConfirmGate` has NO
bulk-approve method. There is no API surface on this class that lets a
caller mark more than one `needs_confirm` item cleared per call. An agent
that wants to skip the per-item gate has to either not call
`require_cleared()` at all (a code-review-visible omission, not a runtime
judgment call) or fabricate a fake per-item ack (an auditable, falsifiable
act, not a private reasoning step) — both are a much higher bar than "reason
that a blanket yes covers it," which is all the old (prose-only) gate
required.
"""


class ConfirmNotRecordedError(RuntimeError):
    """Raised by ConfirmGate.require_cleared() when the given item has no
    recorded, approved, PER-ITEM acknowledgment. There is deliberately no
    way to satisfy this via a blanket/global approval — see module docstring."""


class ConfirmGate:
    """Tracks `needs_confirm` items and the explicit per-item acks recorded
    against them. `require_cleared(item_id)` is the hard-stop: it raises
    unless THAT EXACT item_id has an `approved` ack on file.

    No bulk-approve method exists on this class by design. If you find
    yourself wanting one, that want is the covenant violation — stop and
    surface it (per Talos's own standing lesson, memory e51a6d38) rather
    than adding a shortcut here."""

    def __init__(self):
        self._needs_confirm = {}  # item_id -> {"kind": str, "message": str}
        self._acks = {}  # item_id -> {"decision": "approved"|"declined", "note": str|None}

    def register(self, item_id, kind, message=""):
        """Record that `item_id` requires an explicit per-item confirm before
        any write against it may proceed. Safe to call more than once for the
        same item_id (idempotent registration; does not clear an existing ack)."""
        self._needs_confirm[item_id] = {"kind": kind, "message": message}

    def record_ack(self, item_id, decision, note=None):
        """Record an explicit acknowledgment for EXACTLY `item_id`. `decision`
        must be 'approved' or 'declined'. Raises KeyError if `item_id` was
        never registered — you cannot pre-ack something that isn't a pending
        confirm yet (prevents accidentally-broad acks recorded speculatively
        before the actual item is known)."""
        if item_id not in self._needs_confirm:
            raise KeyError(
                f"{item_id!r} was never registered via register() — nothing to "
                f"acknowledge. Register the item first, or check for a typo in "
                f"the item_id (paths must match exactly; no prefix/glob acks)."
            )
        if decision not in ("approved", "declined"):
            raise ValueError(f"decision must be 'approved' or 'declined', got {decision!r}")
        self._acks[item_id] = {"decision": decision, "note": note}

    def is_cleared(self, item_id):
        ack = self._acks.get(item_id)
        return ack is not None and ack["decision"] == "approved"

    def require_cleared(self, item_id):
        """THE HARD STOP. Raises ConfirmNotRecordedError unless `item_id` has
        an explicit, approved, per-item ack on file. If `item_id` was never
        registered as needs_confirm in the first place, this is a no-op
        (nothing to gate) — the gate only governs items that were actually
        flagged."""
        if item_id not in self._needs_confirm:
            return
        if not self.is_cleared(item_id):
            reg = self._needs_confirm[item_id]
            raise ConfirmNotRecordedError(
                f"{item_id!r} ({reg['kind']}) is a needs_confirm item with no "
                f"recorded per-item acknowledgment. {reg['message']} "
                f"A blanket or global approval does NOT satisfy this — call "
                f"record_ack({item_id!r}, 'approved') explicitly before writing. "
                f"(LOCK-AMENDMENT 3, finding 5d4bbbf2 F1-confirm.)"
            )

    def pending(self):
        """item_ids that are registered but not yet cleared (approved)."""
        return [item_id for item_id in self._needs_confirm if not self.is_cleared(item_id)]

    def all_registered(self):
        return list(self._needs_confirm)
