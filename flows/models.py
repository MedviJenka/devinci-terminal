"""Typed flow models — a user-designed DAG of catalog nodes.

A Flow is the reusable pipeline: an immutable graph whose nodes each reference a
discovered CatalogNode by its `kind:name` key (see discovery.CatalogNode.key)
and declare their prerequisites via `after`. The model is deliberately storage-
and runtime-agnostic; topo.py validates it and executor.py runs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Flow", "FlowNode"]


@dataclass(frozen=True, slots=True)
class FlowNode:
    """One step in a flow.

    `id` is unique within the flow (the edge label used by `after`); `ref` is the
    catalog key of the node to run, e.g. 'agent:planner' or 'command:release';
    `after` lists the ids of steps that must complete first (the DAG edges).
    """

    id: str
    ref: str
    after: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Flow:
    """An immutable, reusable pipeline: a named DAG of FlowNodes."""

    name: str
    description: str
    nodes: tuple[FlowNode, ...] = field(default_factory=tuple)

    def by_id(self, node_id: str) -> FlowNode | None:
        """Return the node with this id, or None if the flow has no such step."""
        return next((n for n in self.nodes if n.id == node_id), None)

    @property
    def ids(self) -> tuple[str, ...]:
        """Every node id, in declaration order."""
        return tuple(n.id for n in self.nodes)
