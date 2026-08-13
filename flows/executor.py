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

from common.logging import get_logger
from common.result import Err, Ok, Result
from discovery import Catalog
from flows.models import Flow, FlowNode
from flows.topo import topo_layers
from runtime.runner import NodeRunner

__all__ = ["NodeStatus", "NodeEvent", "RunReport", "EventSink", "execute"]

logger = get_logger(__name__)


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
    logger.info("flow_execute_started", flow=flow.name, nodes=len(flow.nodes))
    layers = topo_layers(flow)
    if isinstance(layers, Err):
        logger.error("flow_execute_invalid", flow=flow.name, error=layers.error)
        return layers

    statuses: dict[str, NodeStatus] = {}
    outputs: dict[str, str] = {}

    def emit(event: NodeEvent) -> None:
        if on_event is not None:
            on_event(event)

    for layer_index, layer in enumerate(layers.value):
        runnable = [node for node in layer if _deps_ok(node, statuses)]
        runnable_ids = {node.id for node in runnable}
        for node in layer:
            if node.id not in runnable_ids:
                statuses[node.id] = NodeStatus.SKIPPED
                logger.debug("node_skipped", flow=flow.name, node_id=node.id)
                emit(NodeEvent(node.id, NodeStatus.SKIPPED, "prerequisite did not succeed"))

        logger.debug(
            "layer_started",
            flow=flow.name,
            layer=layer_index,
            node_ids=[n.id for n in runnable],
        )
        results = await asyncio.gather(
            *(_run_node(node, catalog, runner, goal, outputs, emit) for node in runnable)
        )
        for node, (status, output) in zip(runnable, results):
            statuses[node.id] = status
            if output is not None:
                outputs[node.id] = output

    report = RunReport(statuses=statuses, outputs=outputs)
    logger.info("flow_execute_finished", flow=flow.name, ok=report.ok, statuses={
        node_id: status.value for node_id, status in statuses.items()
    })
    return Ok(report)


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
        logger.error("node_run_unresolved", node_id=node.id, ref=node.ref, error=resolved.error)
        emit(NodeEvent(node.id, NodeStatus.FAILED, resolved.error))
        return NodeStatus.FAILED, None

    logger.debug("node_run_started", node_id=node.id, ref=node.ref)
    emit(NodeEvent(node.id, NodeStatus.RUNNING))
    inputs = _compose_inputs(node, goal, outputs)
    outcome = await asyncio.to_thread(runner.run, resolved.value, inputs)

    if isinstance(outcome, Ok):
        logger.info("node_run_succeeded", node_id=node.id, ref=node.ref)
        emit(NodeEvent(node.id, NodeStatus.SUCCEEDED))
        return NodeStatus.SUCCEEDED, outcome.value

    logger.warning("node_run_failed", node_id=node.id, ref=node.ref, error=outcome.error)
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
