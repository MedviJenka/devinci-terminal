"""Behavior of the Flow / FlowNode DAG model — construction and lookups."""

from __future__ import annotations

import pytest

from flows.models import Flow, FlowNode


def _flow() -> Flow:
    return Flow(
        name="ship-feature",
        description="plan, then build+test in parallel, then ship",
        nodes=(
            FlowNode(id="plan", ref="agent:planner"),
            FlowNode(id="build", ref="agent:builder", after=("plan",)),
            FlowNode(id="test", ref="agent:tester", after=("plan",)),
            FlowNode(id="ship", ref="command:release", after=("build", "test")),
        ),
    )


def test_flownode_defaults_to_no_prerequisites() -> None:
    node = FlowNode(id="plan", ref="agent:planner")
    assert node.after == ()


def test_flow_is_immutable() -> None:
    flow = _flow()
    with pytest.raises((AttributeError, TypeError)):
        flow.name = "renamed"  # type: ignore[misc]


def test_by_id_returns_the_matching_node() -> None:
    flow = _flow()
    node = flow.by_id("build")
    assert node is not None
    assert node.ref == "agent:builder"
    assert node.after == ("plan",)


def test_by_id_returns_none_for_unknown_id() -> None:
    assert _flow().by_id("nope") is None


def test_ids_lists_every_node_id_in_order() -> None:
    assert _flow().ids == ("plan", "build", "test", "ship")
