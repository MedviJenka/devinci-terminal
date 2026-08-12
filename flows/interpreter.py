"""Bounded interpreter for a control-flow Graph — the loop/branch executor.

Starting at the entry node it walks the graph one node at a time: run the node,
then choose the outgoing edge. For a conditional (ON_TRUE/ON_FALSE) it judges the
edge's condition against the node output via the injected Condition; for a plain
NEXT it follows the successor; with no outgoing edge the run completes. Back-edges
form loops, kept finite by the graph's per-node `max_visits` cap and an absolute
step bound (reliability rule: every loop bounded, no unbounded while).

Runner and Condition are synchronous and injected — each call is offloaded via
asyncio.to_thread so the interpreter never blocks an event loop, and it never
touches an LLM directly. Structural errors return Err; runtime failures are
recorded in the GraphReport with a `stopped` reason, not raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncio

from common.result import Err, Ok, Result
from discovery import Catalog
from flows.executor import EventSink, NodeEvent, NodeStatus
from flows.graph import Edge, EdgeKind, Graph, GraphNode, validate_graph
from runtime.condition import Condition
from runtime.runner import NodeRunner

__all__ = ["GraphReport", "run_graph"]


@dataclass(frozen=True, slots=True)
class GraphReport:
    """Outcome of a graph run: per-node status/output, visit counts, and path."""

    statuses: dict[str, NodeStatus] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    visits: dict[str, int] = field(default_factory=dict)
    path: tuple[str, ...] = ()
    stopped: str = "completed"  # completed | failed | loop-cap | step-cap | condition-error

    @property
    def ok(self) -> bool:
        return self.stopped == "completed" and all(
            status is NodeStatus.SUCCEEDED for status in self.statuses.values()
        )


async def run_graph(
    graph: Graph,
    catalog: Catalog,
    runner: NodeRunner,
    condition: Condition,
    *,
    goal: str = "",
    on_event: EventSink | None = None,
) -> Result[GraphReport, str]:
    """Execute `graph` from its entry, routing conditionals and bounding loops."""
    valid = validate_graph(graph)
    if isinstance(valid, Err):
        return valid

    def emit(event: NodeEvent) -> None:
        if on_event is not None:
            on_event(event)

    statuses: dict[str, NodeStatus] = {}
    outputs: dict[str, str] = {}
    visits: dict[str, int] = {}
    path: list[str] = []
    stopped = "completed"
    last_output: str | None = None

    current: str | None = graph.entry
    step_cap = graph.max_visits * max(1, len(graph.nodes)) + 1
    steps = 0

    while current is not None:
        if steps >= step_cap:
            stopped = "step-cap"
            break
        steps += 1

        if visits.get(current, 0) >= graph.max_visits:
            stopped = "loop-cap"
            break
        visits[current] = visits.get(current, 0) + 1

        node = graph.by_id(current)
        assert node is not None  # validate_graph guarantees entry/edges resolve

        resolved = catalog.resolve(node.ref)
        if isinstance(resolved, Err):
            statuses[current] = NodeStatus.FAILED
            emit(NodeEvent(current, NodeStatus.FAILED, resolved.error))
            stopped = "failed"
            break

        emit(NodeEvent(current, NodeStatus.RUNNING))
        # Run the node in place `repeat` times (bounded, ≥ 1 by validation); the
        # last output is the one routed onward. Any failure stops the whole run.
        outcome: Result[str, str] | None = None
        for _ in range(node.repeat):
            outcome = await asyncio.to_thread(
                runner.run, resolved.value, _compose_inputs(goal, last_output, node.prompt)
            )
            if isinstance(outcome, Err):
                break
            last_output = outcome.value

        assert outcome is not None  # repeat ≥ 1 guarantees at least one run
        if isinstance(outcome, Err):
            statuses[current] = NodeStatus.FAILED
            emit(NodeEvent(current, NodeStatus.FAILED, outcome.error))
            stopped = "failed"
            break

        statuses[current] = NodeStatus.SUCCEEDED
        outputs[current] = outcome.value
        path.append(current)
        emit(NodeEvent(current, NodeStatus.SUCCEEDED))

        nxt = await _next_node(node, outcome.value, condition)
        if isinstance(nxt, Err):
            stopped = "condition-error"
            emit(NodeEvent(current, NodeStatus.FAILED, nxt.error))
            break
        current = nxt.value

    return Ok(
        GraphReport(
            statuses=statuses,
            outputs=outputs,
            visits=visits,
            path=tuple(path),
            stopped=stopped,
        )
    )


async def _next_node(
    node: GraphNode, output: str, condition: Condition
) -> Result[str | None, str]:
    """Choose the next node id after `node` ran, or None to stop."""
    on_true = _edge_of(node, EdgeKind.ON_TRUE)
    on_false = _edge_of(node, EdgeKind.ON_FALSE)
    if on_true is not None and on_false is not None:
        cond = on_true.condition or on_false.condition
        verdict = await asyncio.to_thread(condition.evaluate, cond, output)
        if isinstance(verdict, Err):
            return verdict
        return Ok(on_true.to if verdict.value else on_false.to)

    nexts = [edge for edge in node.edges if edge.kind is EdgeKind.NEXT]
    if not nexts:
        return Ok(None)
    # v1 follows a single successor; parallel splits are a later addition.
    return Ok(nexts[0].to)


def _edge_of(node: GraphNode, kind: EdgeKind) -> Edge | None:
    return next((edge for edge in node.edges if edge.kind is kind), None)


def _compose_inputs(goal: str, last_output: str | None, prompt: str = "") -> str:
    parts: list[str] = []
    if goal:
        parts.append(goal)
    if last_output:
        parts.append(f"[previous step output]\n{last_output}")
    if prompt:
        parts.append(f"[card prompt]\n{prompt}")
    return "\n\n".join(parts)
