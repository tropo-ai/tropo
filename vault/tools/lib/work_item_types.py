"""WORK_ITEM_TYPES — the flowing-lifecycle record types, in one place.

Governed by dev-spec 1d14b1bf (Lifecycle Value-Map Phase 1). The set previously
lived as a literal inside `tropo-validate.py` and nowhere else, so any other
checker that needed "is this a work item?" either imported a 15k-line module or
kept its own copy. Check 23 in `.tropo/scripts/lib/event_validators.py` needed
exactly this answer and had no way to ask, so it asked the index for EVERY type
and demanded completion events from `os-config` and `chat-session`.

This module is the one declared source both readers consult. It holds no logic
on purpose: a set with a docstring cannot drift from itself.

`lib` is a namespace package spanning `vault/tools/lib` and `.tropo/scripts/lib`,
so `from lib.work_item_types import WORK_ITEM_TYPES` resolves from either side.

(Extracted 2026-08-31 by argus-a165 while curing Check 23's scope. Copying the
literal into the second reader would have installed the exact defect the cure was
filed against — see note bc3925fd.)
"""

WORK_ITEM_TYPES = frozenset({
    'task', 'note', 'decision', 'design-brief', 'design-spec', 'dev-spec',
    'test-spec', 'arch-spec', 'doc-spec', 'project', 'pipeline', 'pipeline-run',
    'release-plan', 'ship-artifact', 'build', 'project-plan', 'test-run',
    'test-scenario', 'research', 'collection', 'vault-ops-spec', 'document', 'activation',
})
