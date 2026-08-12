"""Layered topological sort for a Flow DAG.

`topo_layers` returns the execution waves: layer 0 is every node with no unmet
prerequisites, layer 1 is everything unblocked once layer 0 completes, and so on
— so each layer's nodes may run in parallel. Duplicate ids, dangling `after`
refs, and cycles are returned as Err rather than raised (parse-at-boundary), and
the Kahn's-algorithm loop is bounded by the node count so a malformed graph can
never spin unbounded (reliability rule).
"""

from __future__ import annotations

from common.result import Err, Ok, Result
from flows.models import Flow, FlowNode

__all__ = ["topo_layers"]

Layers = tuple[tuple[FlowNode, ...], ...]


def topo_layers(flow: Flow) -> Result[Layers, str]:
    """Order `flow`'s nodes into parallelizable layers, or explain why it can't."""
    ids = flow.ids
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        return Err(f"duplicate node id(s): {', '.join(dupes)}")

    id_set = set(ids)
    for node in flow.nodes:
        missing = [dep for dep in node.after if dep not in id_set]
        if missing:
            return Err(
                f"node '{node.id}' depends on unknown node(s): {', '.join(missing)}"
            )

    remaining: dict[str, FlowNode] = {n.id: n for n in flow.nodes}
    unmet: dict[str, set[str]] = {n.id: set(n.after) for n in flow.nodes}
    layers: list[tuple[FlowNode, ...]] = []

    # Each layer removes at least one node, so this cannot exceed len(nodes).
    for _ in range(len(flow.nodes)):
        if not remaining:
            break
        ready = sorted(nid for nid, deps in unmet.items() if not deps)
        if not ready:
            return Err(f"flow has a cycle among: {', '.join(sorted(remaining))}")
        layers.append(tuple(remaining[nid] for nid in ready))
        for nid in ready:
            del remaining[nid]
            del unmet[nid]
        for deps in unmet.values():
            deps.difference_update(ready)

    if remaining:  # defensive: unreachable given the bound above
        return Err(f"flow has a cycle among: {', '.join(sorted(remaining))}")

    return Ok(tuple(layers))
