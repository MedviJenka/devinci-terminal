"""Interactive graph construction — the model behind hand-building a flow.

GraphBuilder is the immutable state a TUI mutates as the user drops agent cards as
nodes and wires edges: every operation returns a NEW builder (the old one is never
touched), unknown-node wiring is an Err not a crash, and `build()` runs the result
through validate_graph so a half-wired graph can't masquerade as runnable.
"""

from __future__ import annotations

from common.result import Err, Ok
from flows.builder import GraphBuilder
from flows.graph import EdgeKind, Graph


def test_add_node_derives_id_from_ref_and_first_node_is_entry() -> None:
    result = GraphBuilder().add_node("agent:code-reviewer")
    assert isinstance(result, Ok)
    builder = result.value
    assert builder.node_ids == ("code-reviewer",)
    assert builder.entry == "code-reviewer"


def test_adding_the_same_ref_twice_dedupes_the_id() -> None:
    builder = GraphBuilder().add_node("agent:coder").value.add_node("agent:coder").value
    assert builder.node_ids == ("coder", "coder-2")


def test_add_node_is_immutable() -> None:
    original = GraphBuilder()
    original.add_node("agent:planner")
    assert original.node_ids == ()  # the original builder is untouched


def test_connect_wires_a_typed_edge_and_builds_a_runnable_graph() -> None:
    builder = (
        GraphBuilder(name="ship", description="review then test")
        .add_node("agent:review").value
        .add_node("agent:test").value
    )
    connected = builder.connect("review", "test", EdgeKind.NEXT)
    assert isinstance(connected, Ok)

    built = connected.value.build()
    assert isinstance(built, Ok)
    graph = built.value
    assert isinstance(graph, Graph)
    assert graph.entry == "review"
    review = graph.by_id("review")
    assert review is not None
    assert review.edges[0].to == "test"


def test_connect_to_unknown_node_is_err() -> None:
    builder = GraphBuilder().add_node("agent:review").value
    assert isinstance(builder.connect("review", "ghost"), Err)
    assert isinstance(builder.connect("ghost", "review"), Err)


def test_remove_node_drops_inbound_edges_and_reassigns_entry() -> None:
    builder = (
        GraphBuilder()
        .add_node("agent:a").value
        .add_node("agent:b").value
    )
    builder = builder.connect("a", "b").value
    removed = builder.remove_node("a")
    assert isinstance(removed, Ok)
    b_only = removed.value
    assert b_only.node_ids == ("b",)
    assert b_only.entry == "b"  # entry moved off the removed node


def test_conditional_graph_missing_a_branch_fails_to_build() -> None:
    builder = (
        GraphBuilder()
        .add_node("agent:review").value
        .add_node("agent:test").value
    )
    # Only the ON_TRUE branch wired — validate_graph must reject on build.
    builder = builder.connect("review", "test", EdgeKind.ON_TRUE, "passed").value
    assert isinstance(builder.build(), Err)


def test_build_empty_is_err() -> None:
    assert isinstance(GraphBuilder().build(), Err)


def test_set_repeat_sets_a_nodes_run_count() -> None:
    builder = GraphBuilder().add_node("agent:coder").value
    updated = builder.set_repeat("coder", 3)
    assert isinstance(updated, Ok)
    node = next(n for n in updated.value.nodes if n.id == "coder")
    assert node.repeat == 3


def test_set_repeat_below_one_is_err() -> None:
    builder = GraphBuilder().add_node("agent:coder").value
    assert isinstance(builder.set_repeat("coder", 0), Err)


def test_set_repeat_unknown_node_is_err() -> None:
    assert isinstance(GraphBuilder().set_repeat("ghost", 2), Err)


def test_branch_wires_both_conditional_edges() -> None:
    builder = (
        GraphBuilder(name="ship", description="")
        .add_node("agent:review").value
        .add_node("agent:ship").value
        .add_node("agent:code").value
    )
    branched = builder.branch("review", "ship", "code", "tests passed")
    assert isinstance(branched, Ok)

    review = next(n for n in branched.value.nodes if n.id == "review")
    by_kind = {e.kind: e for e in review.edges}
    assert by_kind[EdgeKind.ON_TRUE].to == "ship"
    assert by_kind[EdgeKind.ON_FALSE].to == "code"
    assert by_kind[EdgeKind.ON_TRUE].condition == "tests passed"
    # A complete conditional builds cleanly.
    assert isinstance(branched.value.build(), Ok)


def test_branch_to_unknown_target_is_err() -> None:
    builder = GraphBuilder().add_node("agent:review").value
    assert isinstance(builder.branch("review", "ghost", "review", "ok"), Err)
