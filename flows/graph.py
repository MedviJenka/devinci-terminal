"""
Control-flow graph model — the evolution of Flow that supports loops + branches.

A Graph is a directed graph whose edges are typed: NEXT for plain sequence, and
ON_TRUE / ON_FALSE for a conditional whose branch is chosen at runtime by judging
the node's output against the edge's natural-language `condition`. Loops need no
special construct — an ON_FALSE edge pointing back to an earlier node IS a loop,
kept finite by the per-node `max_visits` cap (reliability rule: every loop bounded).

`validate_graph` is the structural trust boundary: entry exists, every edge target
exists, ids are unique, and a conditional node declares both branches. It returns
a Result and never raises.
"""

from enum import Enum
from dataclasses import dataclass, field
from common.result import Err, Ok, Result


__all__ = ["EdgeKind", "Edge", "GraphNode", "Graph", "validate_graph"]


# Default hard cap on how many times any single node may execute in one run.
DEFAULT_MAX_VISITS = 5


class EdgeKind(str, Enum):
    """How an outgoing edge is chosen when a node finishes."""

    NEXT = "next"  # unconditional successor
    ON_TRUE = "on_true"  # taken when the condition judges true
    ON_FALSE = "on_false"  # taken when the condition judges false


@dataclass(frozen=True, slots=True)
class Edge:
    """A directed edge to another node. `condition` applies to ON_TRUE/ON_FALSE."""

    to: str
    kind: EdgeKind = EdgeKind.NEXT
    condition: str = ""


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One executable card in a graph.

    `text` is the card's visible branch/instruction label. `prompt` is optional
    per-card guidance appended to the runner input. `repeat` is how many times the
    node runs in place before its edges are routed.
    """

    id: str
    ref: str
    edges: tuple[Edge, ...] = ()
    repeat: int = 1
    text: str = ""
    prompt: str = ""


@dataclass(frozen=True, slots=True)
class Graph:

    """A named control-flow graph with an explicit entry and a loop-visit cap."""

    name: str
    description: str
    entry: str
    nodes: tuple[GraphNode, ...] = field(default_factory=tuple)
    max_visits: int = DEFAULT_MAX_VISITS

    def by_id(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(n.id for n in self.nodes)


def validate_graph(graph: Graph) -> Result[Graph, str]:
    """Check the graph is structurally runnable, or explain what's wrong."""
    ids = graph.ids
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        return Err(f"duplicate node id(s): {', '.join(dupes)}")

    id_set = set(ids)
    if graph.entry not in id_set:
        return Err(f"entry '{graph.entry}' is not a node in the graph")

    if graph.max_visits < 1:
        return Err("max_visits must be at least 1")

    for node in graph.nodes:
        if node.repeat < 1:
            return Err(f"node '{node.id}' has repeat {node.repeat}; must be at least 1")
        for edge in node.edges:
            if edge.to not in id_set:
                return Err(f"node '{node.id}' has an edge to unknown node '{edge.to}'")
        kinds = {edge.kind for edge in node.edges}
        has_true = EdgeKind.ON_TRUE in kinds
        has_false = EdgeKind.ON_FALSE in kinds
        if has_true != has_false:
            missing = "ON_FALSE" if has_true else "ON_TRUE"
            return Err(
                f"conditional node '{node.id}' is missing its {missing} branch"
            )

    return Ok(graph)
