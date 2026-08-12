"""Immutable state for hand-building a control-flow Graph in the TUI.

Where graph_author.py asks a model to design a Graph from a goal, GraphBuilder is
the manual path: the user drops discovered agent cards as nodes and wires edges by
hand. Every mutation returns a NEW GraphBuilder (frozen; the caller keeps an undo
history for free), unknown-node wiring returns an Err instead of raising, and
`build()` funnels through validate_graph so a partially-wired graph can never be
mistaken for a runnable one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from common.result import Err, Ok, Result
from flows.graph import Edge, EdgeKind, Graph, GraphNode, validate_graph

__all__ = ["GraphBuilder"]

# Bound on the dedupe suffix search — far beyond any hand-built graph size.
_MAX_ID_ATTEMPTS = 1000


@dataclass(frozen=True, slots=True)
class GraphBuilder:
    """An in-progress Graph: named nodes, their edges, and the chosen entry."""

    name: str = ""
    description: str = ""
    nodes: tuple[GraphNode, ...] = ()
    entry: str = ""

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def add_node(self, ref: str, node_id: str | None = None) -> Result[GraphBuilder, str]:
        """Append a node running `ref`; the first node added becomes the entry.

        `node_id` defaults to a unique id derived from `ref`. An explicit id that
        already exists is an error.
        """
        if not ref:
            return Err("node ref must not be empty")
        existing = set(self.node_ids)
        if node_id is not None:
            if node_id in existing:
                return Err(f"node id '{node_id}' already exists")
            new_id = node_id
        else:
            new_id = _unique_id(_base_id(ref), existing)
            if new_id is None:
                return Err(f"could not derive a unique id from ref '{ref}'")

        nodes = self.nodes + (GraphNode(id=new_id, ref=ref),)
        entry = self.entry or new_id
        return Ok(replace(self, nodes=nodes, entry=entry))

    def connect(
        self,
        from_id: str,
        to_id: str,
        kind: EdgeKind = EdgeKind.NEXT,
        condition: str = "",
    ) -> Result[GraphBuilder, str]:
        """Add an edge from `from_id` to `to_id`; both nodes must already exist."""
        ids = set(self.node_ids)
        if from_id not in ids:
            return Err(f"no node '{from_id}' to connect from")
        if to_id not in ids:
            return Err(f"no node '{to_id}' to connect to")

        edge = Edge(to=to_id, kind=kind, condition=condition)
        nodes = tuple(
            replace(node, edges=node.edges + (edge,)) if node.id == from_id else node
            for node in self.nodes
        )
        return Ok(replace(self, nodes=nodes))

    def set_repeat(self, node_id: str, times: int) -> Result[GraphBuilder, str]:
        """Set how many times `node_id` runs in place (must be ≥ 1)."""
        if node_id not in set(self.node_ids):
            return Err(f"no node '{node_id}' to repeat")
        if times < 1:
            return Err(f"repeat must be at least 1, got {times}")
        nodes = tuple(
            replace(node, repeat=times) if node.id == node_id else node
            for node in self.nodes
        )
        return Ok(replace(self, nodes=nodes))

    def branch(
        self, from_id: str, true_to: str, false_to: str, condition: str
    ) -> Result[GraphBuilder, str]:
        """Make `from_id` an if/else node: ON_TRUE→true_to, ON_FALSE→false_to.

        Replaces the node's existing outgoing edges with exactly the two branches,
        so a plain node (e.g. one auto-chained with NEXT) converts cleanly. All
        three ids must exist; a false-branch pointing to an earlier node is a loop.
        """
        ids = set(self.node_ids)
        for label, target in (("from", from_id), ("true", true_to), ("false", false_to)):
            if target not in ids:
                return Err(f"branch {label} target '{target}' is not a node")
        branches = (
            Edge(to=true_to, kind=EdgeKind.ON_TRUE, condition=condition),
            Edge(to=false_to, kind=EdgeKind.ON_FALSE, condition=condition),
        )
        nodes = tuple(
            replace(node, edges=branches) if node.id == from_id else node
            for node in self.nodes
        )
        return Ok(replace(self, nodes=nodes))

    def remove_node(self, node_id: str) -> Result[GraphBuilder, str]:
        """Drop a node and every edge pointing at it; reassign entry if needed."""
        if node_id not in set(self.node_ids):
            return Err(f"no node '{node_id}' to remove")
        nodes = tuple(
            replace(node, edges=tuple(e for e in node.edges if e.to != node_id))
            for node in self.nodes
            if node.id != node_id
        )
        entry = self.entry
        if entry == node_id:
            entry = nodes[0].id if nodes else ""
        return Ok(replace(self, nodes=nodes, entry=entry))

    def build(self) -> Result[Graph, str]:
        """Assemble and structurally validate the Graph, or explain what's wrong."""
        graph = Graph(
            name=self.name,
            description=self.description,
            entry=self.entry,
            nodes=self.nodes,
        )
        return validate_graph(graph)


def _base_id(ref: str) -> str:
    """Strip the 'kind:' prefix from a catalog ref: 'agent:coder' -> 'coder'."""
    return ref.split(":", 1)[1] if ":" in ref else ref


def _unique_id(base: str, taken: set[str]) -> str | None:
    """`base`, else base-2, base-3, … — first id not already in `taken`."""
    if base not in taken:
        return base
    for suffix in range(2, _MAX_ID_ATTEMPTS + 1):
        candidate = f"{base}-{suffix}"
        if candidate not in taken:
            return candidate
    return None
