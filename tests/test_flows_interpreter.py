"""Bounded control-flow interpreter — walk edges, judge conditions, cap loops.

Runner and condition-evaluator are injected, so these tests use fakes: no LLM,
fully deterministic. They cover sequence, both conditional branches, a bounded
loop that converges, a loop that hits its cap, and failure/condition-error stops.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.result import Err, Ok, Result
from discovery import Catalog, CatalogNode, NodeKind
from flows.executor import NodeStatus
from flows.graph import Edge, EdgeKind, Graph, GraphNode
from flows.interpreter import run_graph


def _catalog(*names: str) -> Catalog:
    catalog = Catalog()
    for name in names:
        catalog.add(
            CatalogNode(
                kind=NodeKind.AGENT,
                name=name,
                description=f"{name}",
                source=Path(f"/fake/{name}.md"),
            )
        )
    return catalog


class FakeRunner:
    def __init__(self, fail: set[str] | None = None) -> None:
        self._fail = fail or set()
        self.calls: list[str] = []
        self.inputs: list[tuple[str, str]] = []

    def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
        self.calls.append(node.name)
        self.inputs.append((node.name, inputs))
        if node.name in self._fail:
            return Err(f"{node.name} boom")
        return Ok(f"out:{node.name}")


class FakeCondition:
    """Returns scripted verdicts in order; clamps to the last once exhausted."""

    def __init__(self, verdicts: list[bool] | Result[bool, str]) -> None:
        self._verdicts = verdicts
        self._i = 0

    def evaluate(self, condition: str, output: str) -> Result[bool, str]:
        if isinstance(self._verdicts, (Ok, Err)):
            return self._verdicts
        v = self._verdicts[min(self._i, len(self._verdicts) - 1)]
        self._i += 1
        return Ok(v)


def _linear() -> Graph:
    return Graph(
        name="lin",
        description="",
        entry="a",
        nodes=(
            GraphNode("a", "agent:a", edges=(Edge(to="b"),)),
            GraphNode("b", "agent:b", edges=(Edge(to="c"),)),
            GraphNode("c", "agent:c"),
        ),
    )


def _loop(max_visits: int = 5) -> Graph:
    # code -> review; review pass -> done, review fail -> code (loop back)
    return Graph(
        name="loop",
        description="",
        entry="code",
        max_visits=max_visits,
        nodes=(
            GraphNode("code", "agent:code", edges=(Edge(to="review"),)),
            GraphNode(
                "review",
                "agent:review",
                edges=(
                    Edge(to="done", kind=EdgeKind.ON_TRUE, condition="passed"),
                    Edge(to="code", kind=EdgeKind.ON_FALSE, condition="passed"),
                ),
            ),
            GraphNode("done", "agent:done"),
        ),
    )


@pytest.mark.asyncio
async def test_linear_sequence_runs_in_order_and_completes() -> None:
    result = await run_graph(
        _linear(), _catalog("a", "b", "c"), FakeRunner(), FakeCondition([])
    )
    assert isinstance(result, Ok)
    report = result.value
    assert report.ok
    assert report.path == ("a", "b", "c")
    assert report.stopped == "completed"


@pytest.mark.asyncio
async def test_conditional_true_takes_on_true_branch() -> None:
    result = await run_graph(
        _loop(), _catalog("code", "review", "done"), FakeRunner(), FakeCondition([True])
    )
    assert isinstance(result, Ok)
    assert result.value.path == ("code", "review", "done")


@pytest.mark.asyncio
async def test_loop_converges_when_condition_eventually_true() -> None:
    result = await run_graph(
        _loop(),
        _catalog("code", "review", "done"),
        FakeRunner(),
        FakeCondition([False, False, True]),
    )
    assert isinstance(result, Ok)
    report = result.value
    assert report.stopped == "completed"
    assert report.visits["code"] == 3
    assert report.path[-1] == "done"


@pytest.mark.asyncio
async def test_loop_hits_cap_when_condition_never_true() -> None:
    result = await run_graph(
        _loop(max_visits=2),
        _catalog("code", "review", "done"),
        FakeRunner(),
        FakeCondition([False]),
    )
    assert isinstance(result, Ok)
    report = result.value
    assert report.stopped == "loop-cap"
    assert not report.ok
    assert report.visits["code"] <= 2


@pytest.mark.asyncio
async def test_runner_failure_stops_the_run() -> None:
    result = await run_graph(
        _linear(), _catalog("a", "b", "c"), FakeRunner(fail={"b"}), FakeCondition([])
    )
    assert isinstance(result, Ok)
    report = result.value
    assert report.stopped == "failed"
    assert report.statuses["b"] is NodeStatus.FAILED
    assert "c" not in report.statuses


@pytest.mark.asyncio
async def test_condition_error_stops_the_run() -> None:
    result = await run_graph(
        _loop(),
        _catalog("code", "review", "done"),
        FakeRunner(),
        FakeCondition(Err("judge unavailable")),
    )
    assert isinstance(result, Ok)
    assert result.value.stopped == "condition-error"


@pytest.mark.asyncio
async def test_repeat_runs_a_node_in_place_n_times() -> None:
    graph = Graph(
        name="rep",
        description="",
        entry="a",
        nodes=(
            GraphNode("a", "agent:a", edges=(Edge(to="b"),), repeat=3),
            GraphNode("b", "agent:b"),
        ),
    )
    runner = FakeRunner()
    result = await run_graph(graph, _catalog("a", "b"), runner, FakeCondition([]))

    assert isinstance(result, Ok)
    report = result.value
    assert report.ok
    # 'a' ran three times before advancing to 'b', which ran once.
    assert runner.calls == ["a", "a", "a", "b"]
    # It is still one node visit, not three (repeat is in-place, not a loop).
    assert report.visits["a"] == 1
    assert report.path == ("a", "b")


@pytest.mark.asyncio
async def test_node_prompt_is_included_in_runner_inputs() -> None:
    graph = Graph(
        name="prompted",
        description="ship the feature",
        entry="review",
        nodes=(GraphNode("review", "agent:review", prompt="focus on regression risk"),),
    )
    runner = FakeRunner()
    result = await run_graph(
        graph, _catalog("review"), runner, FakeCondition([]), goal="ship the feature"
    )

    assert isinstance(result, Ok)
    assert "ship the feature" in runner.inputs[0][1]
    assert "focus on regression risk" in runner.inputs[0][1]



@pytest.mark.asyncio
async def test_repeat_stops_the_run_on_first_failure() -> None:
    graph = Graph(
        name="rep",
        description="",
        entry="a",
        nodes=(GraphNode("a", "agent:a", repeat=5),),
    )
    runner = FakeRunner(fail={"a"})
    result = await run_graph(graph, _catalog("a"), runner, FakeCondition([]))

    assert isinstance(result, Ok)
    assert result.value.stopped == "failed"
    # Failed on the first attempt — no further repeats.
    assert runner.calls == ["a"]


@pytest.mark.asyncio
async def test_invalid_graph_is_err() -> None:
    bad = Graph(name="x", description="", entry="ghost", nodes=(GraphNode("a", "agent:a"),))
    result = await run_graph(bad, _catalog("a"), FakeRunner(), FakeCondition([]))
    assert isinstance(result, Err)


@pytest.mark.asyncio
async def test_unknown_ref_fails_that_node() -> None:
    graph = Graph(
        name="x", description="", entry="a", nodes=(GraphNode("a", "agent:missing"),)
    )
    result = await run_graph(graph, _catalog("present"), FakeRunner(), FakeCondition([]))
    assert isinstance(result, Ok)
    assert result.value.statuses["a"] is NodeStatus.FAILED
