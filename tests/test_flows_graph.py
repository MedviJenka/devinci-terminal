"""Control-flow graph model — nodes, typed edges, lookups, structural validation.

Unlike the pure-DAG Flow, a Graph has an explicit entry, typed edges (NEXT for
sequence, ON_TRUE/ON_FALSE for conditionals), and a per-node visit cap that
bounds loops formed by back-edges. Validation is a Result, never a raise.
"""

from __future__ import annotations

from common.result import Err, Ok
from flows.graph import Edge, EdgeKind, Graph, GraphNode, validate_graph


def _example() -> Graph:
    # prd -> code -> review; review pass -> test, review fail -> code (loop)
    return Graph(
        name="ship",
        description="prd then code/review loop then test",
        entry="prd",
        nodes=(
            GraphNode(id="prd", ref="agent:prd", edges=(Edge(to="code"),)),
            GraphNode(id="code", ref="agent:code", edges=(Edge(to="review"),)),
            GraphNode(
                id="review",
                ref="agent:review",
                edges=(
                    Edge(to="test", kind=EdgeKind.ON_TRUE, condition="review passed"),
                    Edge(to="code", kind=EdgeKind.ON_FALSE, condition="review passed"),
                ),
            ),
            GraphNode(id="test", ref="agent:test"),
        ),
    )


def test_by_id_and_ids() -> None:
    graph = _example()
    assert graph.ids == ("prd", "code", "review", "test")
    assert graph.by_id("review").ref == "agent:review"
    assert graph.by_id("ghost") is None


def test_edge_defaults_to_next_kind() -> None:
    assert Edge(to="x").kind is EdgeKind.NEXT


def test_default_max_visits_bounds_loops() -> None:
    # A sane default cap must exist so back-edges can't loop forever.
    assert _example().max_visits >= 1


def test_valid_graph_passes_validation() -> None:
    assert isinstance(validate_graph(_example()), Ok)


def test_missing_entry_is_err() -> None:
    graph = Graph(name="x", description="", entry="ghost", nodes=(GraphNode("a", "agent:a"),))
    result = validate_graph(graph)
    assert isinstance(result, Err)
    assert "entry" in result.error.lower()


def test_edge_to_unknown_node_is_err() -> None:
    graph = Graph(
        name="x",
        description="",
        entry="a",
        nodes=(GraphNode("a", "agent:a", edges=(Edge(to="ghost"),)),),
    )
    result = validate_graph(graph)
    assert isinstance(result, Err)
    assert "ghost" in result.error


def test_duplicate_ids_is_err() -> None:
    graph = Graph(
        name="x",
        description="",
        entry="a",
        nodes=(GraphNode("a", "agent:a"), GraphNode("a", "agent:b")),
    )
    result = validate_graph(graph)
    assert isinstance(result, Err)
    assert "duplicate" in result.error.lower()


def test_node_repeat_defaults_to_one() -> None:
    assert GraphNode(id="a", ref="agent:a").repeat == 1

def test_node_text_and_prompt_default_to_empty_strings() -> None:
    node = GraphNode(id="a", ref="agent:a")
    assert node.text == ""
    assert node.prompt == ""


def test_node_accepts_branch_card_text_and_optional_prompt() -> None:
    node = GraphNode(
        id="if-qa",
        ref="agent:reviewer",
        text="if the patch needs QA",
        prompt="focus on regression risk",
    )
    assert node.text == "if the patch needs QA"
    assert node.prompt == "focus on regression risk"



def test_repeat_below_one_is_err() -> None:
    graph = Graph(
        name="x",
        description="",
        entry="a",
        nodes=(GraphNode("a", "agent:a", repeat=0),),
    )
    result = validate_graph(graph)
    assert isinstance(result, Err)
    assert "repeat" in result.error.lower()
    assert "a" in result.error


def test_positive_repeat_passes_validation() -> None:
    graph = Graph(
        name="x",
        description="",
        entry="a",
        nodes=(GraphNode("a", "agent:a", repeat=3),),
    )
    assert isinstance(validate_graph(graph), Ok)


def test_conditional_node_needs_both_branches() -> None:
    # A node with ON_TRUE but no ON_FALSE (or vice versa) is a dead conditional.
    graph = Graph(
        name="x",
        description="",
        entry="a",
        nodes=(
            GraphNode(
                "a",
                "agent:a",
                edges=(Edge(to="b", kind=EdgeKind.ON_TRUE, condition="ok"),),
            ),
            GraphNode("b", "agent:b"),
        ),
    )
    result = validate_graph(graph)
    assert isinstance(result, Err)
    assert "a" in result.error
