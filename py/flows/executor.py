"""Execute a flow DAG — run each layer's nodes concurrently, stream events.

`execute` topo-sorts the flow into parallel layers (topo.py) and walks them: a
node runs only when every prerequisite succeeded, otherwise it is skipped, so one
failure contains its own branch without stalling independent work. Each node's
inputs are the run goal plus its upstream outputs, so a pipeline actually pipes.

Runners are synchronous and (per SingleAgentFactory) must not be called inside a
running event loop, so each run is offloaded via asyncio.to_thread. The NodeRunner
is injected — the executor never constructs a backend or touches an LLM directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from common.result import Err, Ok, Result
from discovery import Catalog
from flows.models import Flow, FlowNode
from flows.topo import topo_layers
from runtime.runner import NodeRunner

__all__ = ["NodeStatus", "NodeEvent", "RunReport", "EventSink", "execute"]


class NodeStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class NodeEvent:
    """A single status transition for one node, streamed to an optional sink."""

    node_id: str
    status: NodeStatus
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RunReport:
    """The terminal status and output of every node after a run completes."""

    statuses: dict[str, NodeStatus] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.statuses) and all(
            status is NodeStatus.SUCCEEDED for status in self.statuses.values()
        )


EventSink = Callable[[NodeEvent], None]


async def execute(
    flow: Flow,
    catalog: Catalog,
    runner: NodeRunner,
    *,
    goal: str = "",
    on_event: EventSink | None = None,
) -> Result[RunReport, str]:
    """Run `flow`, resolving each node against `catalog` and running via `runner`.

    Returns Err only when the flow itself is invalid (cycle/dangling ref); a node
    that fails at runtime is recorded in the report, not raised.
    """
    layers = topo_layers(flow)
    if isinstance(layers, Err):
        return layers

    statuses: dict[str, NodeStatus] = {}
    outputs: dict[str, str] = {}

    def emit(event: NodeEvent) -> None:
        if on_event is not None:
            on_event(event)

    for layer in layers.value:
        runnable = [node for node in layer if _deps_ok(node, statuses)]
        runnable_ids = {node.id for node in runnable}
        for node in layer:
            if node.id not in runnable_ids:
                statuses[node.id] = NodeStatus.SKIPPED
                emit(NodeEvent(node.id, NodeStatus.SKIPPED, "prerequisite did not succeed"))

        results = await asyncio.gather(
            *(_run_node(node, catalog, runner, goal, outputs, emit) for node in runnable)
        )
        for node, (status, output) in zip(runnable, results):
            statuses[node.id] = status
            if output is not None:
                outputs[node.id] = output

    return Ok(RunReport(statuses=statuses, outputs=outputs))


def _deps_ok(node: FlowNode, statuses: dict[str, NodeStatus]) -> bool:
    return all(statuses.get(dep) is NodeStatus.SUCCEEDED for dep in node.after)


async def _run_node(
    node: FlowNode,
    catalog: Catalog,
    runner: NodeRunner,
    goal: str,
    outputs: dict[str, str],
    emit: EventSink,
) -> tuple[NodeStatus, str | None]:
    resolved = catalog.resolve(node.ref)
    if isinstance(resolved, Err):
        emit(NodeEvent(node.id, NodeStatus.FAILED, resolved.error))
        return NodeStatus.FAILED, None

    emit(NodeEvent(node.id, NodeStatus.RUNNING))
    inputs = _compose_inputs(node, goal, outputs)
    outcome = await asyncio.to_thread(runner.run, resolved.value, inputs)

    if isinstance(outcome, Ok):
        emit(NodeEvent(node.id, NodeStatus.SUCCEEDED))
        return NodeStatus.SUCCEEDED, outcome.value

    emit(NodeEvent(node.id, NodeStatus.FAILED, outcome.error))
    return NodeStatus.FAILED, None


def _compose_inputs(node: FlowNode, goal: str, outputs: dict[str, str]) -> str:
    parts: list[str] = []
    if goal:
        parts.append(goal)
    for dep in node.after:
        if dep in outputs:
            parts.append(f"[from {dep}]\n{outputs[dep]}")
    return "\n\n".join(parts)
