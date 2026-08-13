"""Graph persistence — hand-built control-flow graphs saved/loaded as YAML.

Graphs carry more than a Flow (typed edges, loops, per-node repeat), so they get
their own store and their own directory. Loading is a trust boundary: malformed
files are rejected with an Err and skipped by the directory listing.
"""

from __future__ import annotations

from pathlib import Path

from common.result import Err, Ok
from flows import list_graphs, load_graph, save_graph
from flows.graph import Edge, EdgeKind, Graph, GraphNode


def _branchy_graph() -> Graph:
    return Graph(
        name="ship",
        description="plan, build, then verify or fix",
        entry="plan",
        max_visits=5,
        nodes=(
            GraphNode(id="plan", ref="agent:planner", edges=(Edge(to="build"),)),
            GraphNode(
                id="build",
                ref="agent:coder",
                repeat=2,
                prompt="write the code",
                edges=(
                    Edge(to="verify", kind=EdgeKind.ON_TRUE, condition="compiles"),
                    Edge(to="build", kind=EdgeKind.ON_FALSE, condition="compiles"),
                ),
            ),
            GraphNode(id="verify", ref="agent:tester", text="run the suite"),
        ),
    )


def test_save_then_load_roundtrips_the_graph(tmp_path: Path) -> None:
    graphs_dir = tmp_path / ".devinci" / "graphs"

    saved = save_graph(_branchy_graph(), graphs_dir)

    assert isinstance(saved, Ok)
    assert saved.value == graphs_dir / "ship.yaml"

    loaded = load_graph(saved.value)
    assert isinstance(loaded, Ok)
    assert loaded.value == _branchy_graph()


def test_load_rejects_a_structurally_invalid_graph(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir(parents=True)
    # entry points at a node that does not exist — validate_graph must catch it.
    (graphs_dir / "broken.yaml").write_text(
        "name: broken\ndescription: ''\nentry: ghost\nnodes:\n"
        "  - id: plan\n    ref: agent:planner\n",
        encoding="utf-8",
    )

    result = load_graph(graphs_dir / "broken.yaml")
    assert isinstance(result, Err)


def test_list_graphs_loads_valid_and_skips_malformed(tmp_path: Path) -> None:
    graphs_dir = tmp_path / "graphs"
    save_graph(_branchy_graph(), graphs_dir)
    (graphs_dir / "junk.yaml").write_text("not: a graph\n", encoding="utf-8")

    graphs = list_graphs(graphs_dir)

    assert tuple(g.name for g in graphs) == ("ship",)


def test_list_graphs_is_empty_for_a_missing_directory(tmp_path: Path) -> None:
    assert list_graphs(tmp_path / "nope") == ()
