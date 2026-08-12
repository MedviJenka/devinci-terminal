"""Layered topological sort — the order the executor runs a DAG in.

Each layer is a set of nodes whose prerequisites are all satisfied, so every
node in a layer may run in parallel. Cycles and dangling `after` refs are
reported as Err (parse-at-boundary), never raised.
"""

from __future__ import annotations

from common.result import Err, Ok
from flows.models import Flow, FlowNode
from flows.topo import topo_layers


def _layer_ids(layers: tuple[tuple[FlowNode, ...], ...]) -> list[set[str]]:
    return [{n.id for n in layer} for layer in layers]


def test_diamond_dag_sorts_into_parallel_layers() -> None:
    flow = Flow(
        name="diamond",
        description="",
        nodes=(
            FlowNode(id="plan", ref="agent:planner"),
            FlowNode(id="build", ref="agent:builder", after=("plan",)),
            FlowNode(id="test", ref="agent:tester", after=("plan",)),
            FlowNode(id="ship", ref="command:release", after=("build", "test")),
        ),
    )

    result = topo_layers(flow)

    assert isinstance(result, Ok)
    assert _layer_ids(result.value) == [{"plan"}, {"build", "test"}, {"ship"}]


def test_independent_nodes_all_land_in_the_first_layer() -> None:
    flow = Flow(
        name="fan",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a"),
            FlowNode(id="b", ref="agent:b"),
            FlowNode(id="c", ref="agent:c"),
        ),
    )

    result = topo_layers(flow)

    assert isinstance(result, Ok)
    assert _layer_ids(result.value) == [{"a", "b", "c"}]


def test_cycle_is_reported_as_err() -> None:
    flow = Flow(
        name="cyclic",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a", after=("b",)),
            FlowNode(id="b", ref="agent:b", after=("a",)),
        ),
    )

    result = topo_layers(flow)

    assert isinstance(result, Err)
    assert "cycle" in result.error.lower()


def test_dangling_after_ref_is_reported_as_err() -> None:
    flow = Flow(
        name="dangling",
        description="",
        nodes=(FlowNode(id="a", ref="agent:a", after=("ghost",)),),
    )

    result = topo_layers(flow)

    assert isinstance(result, Err)
    assert "ghost" in result.error


def test_duplicate_node_ids_are_reported_as_err() -> None:
    flow = Flow(
        name="dupe",
        description="",
        nodes=(
            FlowNode(id="a", ref="agent:a"),
            FlowNode(id="a", ref="agent:b"),
        ),
    )

    result = topo_layers(flow)

    assert isinstance(result, Err)
    assert "duplicate" in result.error.lower()
