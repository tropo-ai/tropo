"""lib/ref_closure.py — the vault-scoped, exclusion-aware, re-runnable
changeset / reference-closure query.

Dev-spec 3c13977e §Read Contract item 5 (§6.5); cycle brief cc437616 §3/§4;
test-spec c56b9cc0 assertion A6. Also the query behind c27c741b §3C's
"count-first, prune-is-a-graph-op" publish panel.

Given a selection of items to publish, return the TRANSITIVE closure of
UNPUBLISHED references that must publish with them (so teammates never hit dead
links). The query is:

  - vault-scoped        — a cross-vault selection is REFUSED (never a cross-vault
                          closure); a ref that crosses into another vault is an
                          EXTERNAL DEPENDENCY PIN, not part of the closure
                          (cc437616 §3: publish the referenced vault first, use
                          separate receipts, do not claim atomicity);
  - exclusion-aware     — supply an exclusion set to hold nodes back;
  - re-runnable         — prune is a GRAPH operation, not a per-row toggle:
                          re-running with an exclusion recomputes the closure,
                          returns the newly CUT EDGES, and reports any subtree
                          left STRANDED (reachable only through an excluded node).

Pure over an injected graph so it is fully unit-testable without the index; a
best-effort index adapter builds the graph from the derived store's edges.
Traversal STOPS at published nodes (an already-shared ref needs no re-publish)
and never enters another vault.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class GraphNode:
    """One node in the closure graph. `refs` are the outbound reference edges
    (targets that must be present for this node not to dangle)."""
    uid: str
    vault_uid: str
    published: bool
    refs: tuple[str, ...] = ()


@dataclass
class ClosureResult:
    refused: bool
    reason: Optional[str] = None
    vault_uid: Optional[str] = None
    snapshot_revision: Optional[str] = None
    selection: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    included_nodes: list[str] = field(default_factory=list)
    cut_edges: list[list[str]] = field(default_factory=list)
    stranded_nodes: list[str] = field(default_factory=list)
    external_dependency_pins: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "refused": self.refused,
            "reason": self.reason,
            "vault_uid": self.vault_uid,
            "snapshot_revision": self.snapshot_revision,
            "selection": self.selection,
            "exclusions": self.exclusions,
            "included_nodes": self.included_nodes,
            "cut_edges": self.cut_edges,
            "stranded_nodes": self.stranded_nodes,
            "external_dependency_pins": self.external_dependency_pins,
        }


def _reachable(
    graph: Mapping[str, GraphNode],
    seeds: Iterable[str],
    vault_uid: str,
    exclusions: frozenset[str],
) -> set[str]:
    """Transitive closure of unpublished refs from `seeds`, staying inside
    `vault_uid`, never traversing into or including an excluded node, and
    stopping at published nodes."""
    included: set[str] = set()
    stack = [s for s in seeds if s not in exclusions]
    included.update(stack)
    while stack:
        node = graph[stack.pop()]
        for dst in node.refs:
            target = graph.get(dst)
            if target is None:
                continue  # dangling ref — reported separately, not traversed
            if dst in exclusions:
                continue
            if target.vault_uid != vault_uid:
                continue  # cross-vault → external pin, never in the closure
            if target.published:
                continue  # already shared — needs no re-publish
            if dst not in included:
                included.add(dst)
                stack.append(dst)
    return included


def compute_ref_closure(
    graph: Mapping[str, GraphNode],
    selection: Iterable[str],
    *,
    exclusions: Iterable[str] = (),
    snapshot_revision: Optional[str] = None,
) -> ClosureResult:
    """Compute the vault-scoped, exclusion-aware ref closure for a selection.

    Refuses (never returns a partial closure) when: the selection is empty, a
    selected uid is unknown, or the selection spans more than one vault
    (multi-vault changesets are refused — cc437616 §3 / 5d3ab142 §4).
    """
    selection = list(dict.fromkeys(selection))  # de-dupe, preserve order
    exclusion_set = frozenset(exclusions)

    if not selection:
        return ClosureResult(refused=True, reason="empty selection")

    unknown = [u for u in selection if u not in graph]
    if unknown:
        return ClosureResult(
            refused=True, reason=f"selection references unknown nodes: {sorted(unknown)}"
        )

    vaults = {graph[u].vault_uid for u in selection}
    if len(vaults) > 1:
        return ClosureResult(
            refused=True,
            reason=(
                f"cross-vault selection refused (spans {sorted(vaults)}); "
                f"multi-vault changesets are not allowed — publish each vault "
                f"separately (cc437616 §3)"
            ),
        )
    vault_uid = next(iter(vaults))

    reachable_all = _reachable(graph, selection, vault_uid, frozenset())
    reachable_incl = _reachable(graph, selection, vault_uid, exclusion_set)
    included = reachable_incl

    # Stranded: nodes that were reachable before the exclusion but are now
    # unreachable because their only path ran through an excluded node.
    stranded = sorted((reachable_all - reachable_incl) - exclusion_set)

    # Cut edges: outbound refs from an INCLUDED node to a held-back (excluded)
    # node — the links the UI must show as severed when the human prunes.
    cut_edges: list[list[str]] = []
    external_pins: list[dict] = []
    for uid in sorted(included):
        for dst in graph[uid].refs:
            target = graph.get(dst)
            if target is None:
                continue
            if target.vault_uid != vault_uid:
                external_pins.append({
                    "from": uid, "node": dst, "vault_uid": target.vault_uid,
                    "published": target.published,
                })
            elif dst in exclusion_set:
                cut_edges.append([uid, dst])

    return ClosureResult(
        refused=False,
        vault_uid=vault_uid,
        snapshot_revision=snapshot_revision,
        selection=sorted(selection),
        exclusions=sorted(exclusion_set),
        included_nodes=sorted(included),
        cut_edges=sorted(cut_edges),
        stranded_nodes=stranded,
        external_dependency_pins=sorted(
            external_pins, key=lambda p: (p["from"], p["node"])
        ),
    )


__all__ = ["GraphNode", "ClosureResult", "compute_ref_closure"]
