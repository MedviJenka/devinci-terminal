"""Blueprint canvas renderer — draws a control-flow graph as a horizontal box strip.

Pure rendering: build a Rich renderable and rasterize it to text to assert what a
viewer sees — node boxes, connectors, `(if)`/`(else)` fork labels, loop markers,
and live status glyphs.
"""

from __future__ import annotations

from rich.console import Console

from flows.executor import NodeStatus
from flows.graph import Edge, EdgeKind, Graph, GraphNode
from tui.blueprint import render_blueprint


def _plain(renderable: object, *, width: int = 120) -> str:
    console = Console(width=width, no_color=True)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _loop_graph() -> Graph:
    return Graph(
        name="ship",
        description="",
        entry="prd",
        nodes=(
            GraphNode("prd", "agent:prd", edges=(Edge(to="code"),)),
            GraphNode("code", "agent:code", edges=(Edge(to="review"),)),
            GraphNode(
                "review",
                "agent:review",
                edges=(
                    Edge(to="test", kind=EdgeKind.ON_TRUE, condition="passed"),
                    Edge(to="code", kind=EdgeKind.ON_FALSE, condition="passed"),
                ),
            ),
            GraphNode("test", "agent:test"),
        ),
    )


def test_renders_each_node_as_a_card() -> None:
    text = _plain(render_blueprint(_loop_graph()))
    # Rounded cards are drawn with box-drawing borders; id + ref both appear.
    assert "╭" in text and "│" in text
    for token in ("prd", "code", "review", "agent:review"):
        assert token in text


def test_conditional_node_forks_into_if_and_else() -> None:
    text = _plain(render_blueprint(_loop_graph()))
    assert "(if)" in text and "(else)" in text
    # review branches to test (if) and back to code (else).
    assert "test" in text and "code" in text


def test_back_edge_branch_target_is_marked_as_a_loop() -> None:
    # review's else branch loops back to code (an earlier node) → ↻ on that card.
    text = _plain(render_blueprint(_loop_graph()))
    assert "↻" in text


def test_forward_chain_has_no_loop_marker() -> None:
    graph = Graph(
        name="chain",
        description="",
        entry="a",
        nodes=(
            GraphNode("a", "agent:a", edges=(Edge(to="b"),)),
            GraphNode("b", "agent:b"),
        ),
    )
    text = _plain(render_blueprint(graph))
    assert "↻" not in text and "loop" not in text.lower()


def test_entry_node_is_marked() -> None:
    text = _plain(render_blueprint(_loop_graph()))
    assert "▸" in text


def test_repeat_count_is_shown_on_the_box() -> None:
    graph = Graph(
        name="rep",
        description="",
        entry="build",
        nodes=(GraphNode("build", "agent:build", repeat=3),),
    )
    text = _plain(render_blueprint(graph))
    assert "×3" in text


def test_repeat_of_one_is_not_annotated() -> None:
    graph = Graph(
        name="rep",
        description="",
        entry="build",
        nodes=(GraphNode("build", "agent:build"),),
    )
    assert "×" not in _plain(render_blueprint(graph))


def test_live_status_glyph_is_shown_when_provided() -> None:
    statuses = {"prd": NodeStatus.SUCCEEDED, "code": NodeStatus.RUNNING}
    text = _plain(render_blueprint(_loop_graph(), statuses))
    # Succeeded ● and running ◐ glyphs distinguish live nodes from pending ◌.
    assert "●" in text and "◐" in text

def test_many_linear_nodes_wrap_between_cards_in_narrow_terminals() -> None:
    nodes = tuple(
        GraphNode(
            f"qa{i}",
            f"agent:qa-agent-{i}",
            edges=(Edge(to=f"qa{i + 1}"),) if i < 7 else (),
        )
        for i in range(8)
    )
    graph = Graph(name="many", description="", entry="qa0", nodes=nodes)

    text = _plain(render_blueprint(graph), width=80)
    lines = text.splitlines()

    assert all(len(line) <= 80 for line in lines)
    assert sum(line.lstrip().startswith("╭") for line in lines) <= 4
    assert not any(line.strip().startswith(("agent:", "qa", "◌")) for line in lines)


def test_empty_graph_renders_placeholder() -> None:
    graph = Graph(name="empty", description="", entry="", nodes=())
    assert "empty" in _plain(render_blueprint(graph)).lower()
