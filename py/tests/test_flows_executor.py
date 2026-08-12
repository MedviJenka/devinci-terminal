"""Executor behavior — walk a DAG, run nodes via an injected runner, report.

The executor never calls a real LLM: it depends on a NodeRunner interface, so
these tests inject a fake runner and assert on statuses, output threading, event
emission, and failure containment.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from common.result import Err, Ok, Result
from discovery import Catalog, CatalogNode, NodeKind
from flows.executor import NodeEvent, NodeStatus, execute
from flows.models import Flow, FlowNode


def _catalog(*names: str) -> Catalog:
    catalog = Catalog()
    for name in names:
        catalog.add(
            CatalogNode(
                kind=NodeKind.AGENT,
                name=name,
                description=f"{name} agent",
                source=Path(f"/fake/{name}.md"),
            )
        )
    return catalog


class FakeRunner:
    """Records every run and returns a scripted Ok/Err per node name."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self._fail = fail or set()
        self.calls: list[tuple[str, str]] = []

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
        self.calls.append((node.name, inputs))
        if node.name in self._fail:
            return Err(f"{node.name} boom")
        return Ok(f"out:{node.name}")


def _diamond() -> Flow:
    return Flow(
        name="diamond",
        description="",
        nodes=(
            FlowNode(id="plan", ref="agent:plan"),
            FlowNode(id="build", ref="agent:build", after=("plan",)),
            FlowNode(id="test", ref="agent:test", after=("plan",)),
            FlowNode(id="ship", ref="agent:ship", after=("build", "test")),
        ),
    )


@pytest.mark.asyncio
async def test_all_nodes_succeed_and_report_is_ok() -> None:
    catalog = _catalog("plan", "build", "test", "ship")
    result = await execute(_diamond(), catalog, FakeRunner())

    assert isinstance(result, Ok)
    report = result.value
    assert report.ok
    assert set(report.statuses) == {"plan", "build", "test", "ship"}
    assert all(s is NodeStatus.SUCCEEDED for s in report.statuses.values())
    assert report.outputs["ship"] == "out:ship"


@pytest.mark.asyncio
async def test_downstream_node_receives_upstream_output_in_its_inputs() -> None:
    catalog = _catalog("plan", "build", "test", "ship")
    runner = FakeRunner()
    await execute(_diamond(), catalog, runner, goal="GOAL")

    inputs_by_name = {name: inputs for name, inputs in runner.calls}
    assert "GOAL" in inputs_by_name["plan"]
    # ship depends on build+test, so both their outputs feed its inputs.
    assert "out:build" in inputs_by_name["ship"]
    assert "out:test" in inputs_by_name["ship"]


@pytest.mark.asyncio
async def test_failure_skips_dependents_but_not_independent_branches() -> None:
    flow = Flow(
        name="split",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a"),
            FlowNode(id="b", ref="agent:b", after=("a",)),  # depends on failing a
            FlowNode(id="c", ref="agent:c"),  # independent
        ),
    )
    catalog = _catalog("a", "b", "c")
    result = await execute(flow, catalog, FakeRunner(fail={"a"}))

    assert isinstance(result, Ok)
    statuses = result.value.statuses
    assert statuses["a"] is NodeStatus.FAILED
    assert statuses["b"] is NodeStatus.SKIPPED
    assert statuses["c"] is NodeStatus.SUCCEEDED
    assert not result.value.ok


@pytest.mark.asyncio
async def test_unknown_ref_marks_node_failed() -> None:
    flow = Flow(
        name="ghost",
        description="",
        nodes=(FlowNode(id="x", ref="agent:missing"),),
    )
    result = await execute(flow, _catalog("present"), FakeRunner())

    assert isinstance(result, Ok)
    assert result.value.statuses["x"] is NodeStatus.FAILED


@pytest.mark.asyncio
async def test_events_report_running_then_terminal_status() -> None:
    catalog = _catalog("plan", "build", "test", "ship")
    events: list[NodeEvent] = []
    await execute(_diamond(), catalog, FakeRunner(), on_event=events.append)

    # Each node announces RUNNING before its SUCCEEDED.
    for node_id in ("plan", "build", "test", "ship"):
        seq = [e.status for e in events if e.node_id == node_id]
        assert seq == [NodeStatus.RUNNING, NodeStatus.SUCCEEDED]


@pytest.mark.asyncio
async def test_cycle_propagates_as_err() -> None:
    flow = Flow(
        name="cyclic",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a", after=("b",)),
            FlowNode(id="b", ref="agent:b", after=("a",)),
        ),
    )
    result = await execute(flow, _catalog("a", "b"), FakeRunner())
    assert isinstance(result, Err)


@pytest.mark.asyncio
async def test_independent_nodes_run_concurrently() -> None:
    # Two slow independent nodes should overlap: total time < 2x single node.
    class SlowRunner:
        def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
            import time

            time.sleep(0.1)
            return Ok(f"out:{node.name}")

    flow = Flow(
        name="fan",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a"),
            FlowNode(id="b", ref="agent:b"),
        ),
    )
    loop = asyncio.get_running_loop()
    start = loop.time()
    await execute(flow, _catalog("a", "b"), SlowRunner())
    elapsed = loop.time() - start
    assert elapsed < 0.18  # would be ~0.2 if serialized
