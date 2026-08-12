"""The app mounts headless, and its panels render live catalog + flow data."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from common.result import Ok
from discovery import NodeKind, scan
from flows import EdgeKind, Flow, FlowNode, list_flows, save
from tui.app import AgentCards, DeVinciApp, FlowsPanel


def _plain(renderable: object) -> str:
    console = Console(width=100, no_color=True)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    (claude_root / "agents" / "planner.md").write_text(
        "---\nname: planner\ndescription: plans work\n---\nbody\n"
    )
    flows_dir = tmp_path / "flows"
    save(
        Flow(
            name="demo",
            description="d",
            nodes=(FlowNode(id="p", ref="agent:planner"),),
        ),
        flows_dir,
    )
    return claude_root, flows_dir


def test_agent_cards_render_discovered_agents(tmp_path: Path) -> None:
    claude_root, _ = _seed(tmp_path)
    catalog = scan((claude_root,))
    cards = AgentCards()
    node = catalog.find(NodeKind.AGENT, "planner")
    assert node is not None
    rendered = _plain(cards._card(node))
    assert "planner" in rendered
    assert "plans work" in rendered


@pytest.mark.asyncio
async def test_flows_panel_lists_saved_flows_as_options(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(FlowsPanel)
        assert panel.option_count == 1
        assert panel.get_option("demo") is not None


@pytest.mark.asyncio
async def test_flows_panel_shows_disabled_hint_when_no_flows(tmp_path: Path) -> None:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    app = DeVinciApp(roots=(claude_root,), flows_dir=tmp_path / "empty")
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(FlowsPanel)
        assert panel.option_count == 1
        assert panel.get_option_at_index(0).disabled


@pytest.mark.asyncio
async def test_added_nodes_chain_from_the_cursor(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        first = app.add_node_from_card("agent:planner")
        second = app.add_node_from_card("agent:planner")
        assert isinstance(first, Ok)
        assert isinstance(second, Ok)

        builder = second.value
        assert builder.node_ids == ("planner", "planner-2")
        # The cursor advanced to the newest node, and the second node is wired
        # from the first via a NEXT edge (new work attaches from the cursor).
        assert app._cursor == "planner-2"
        head = next(n for n in builder.nodes if n.id == "planner")
        assert [(e.to, e.kind) for e in head.edges] == [
            ("planner-2", EdgeKind.NEXT)
        ]


@pytest.mark.asyncio
async def test_moving_the_cursor_rechains_new_nodes_from_the_selection(
    tmp_path: Path,
) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:planner")  # planner (entry)
        app.add_node_from_card("agent:planner")  # planner-2, cursor here
        moved = app.set_cursor("planner")
        assert isinstance(moved, Ok)
        third = app.add_node_from_card("agent:planner")  # planner-3
        assert isinstance(third, Ok)

        head = next(n for n in third.value.nodes if n.id == "planner")
        # 'planner' now fans out to both the second and third nodes.
        assert {e.to for e in head.edges} == {"planner-2", "planner-3"}
        assert app._cursor == "planner-3"


@pytest.mark.asyncio
async def test_deleting_the_cursor_node_removes_it_and_lands_on_the_left(
    tmp_path: Path,
) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:planner")  # planner (entry)
        app.add_node_from_card("agent:planner")  # planner-2
        app.add_node_from_card("agent:planner")  # planner-3, cursor here

        result = app.delete_node("planner-3")
        assert isinstance(result, Ok)
        assert result.value.node_ids == ("planner", "planner-2")
        # The cursor lands on the deleted node's left neighbour, so the next
        # added card chains from there rather than a dangling reference.
        assert app._cursor == "planner-2"


@pytest.mark.asyncio
async def test_deleting_a_node_drops_edges_that_point_at_it(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:planner")  # planner (entry)
        app.add_node_from_card("agent:planner")  # planner-2 (planner → planner-2)

        result = app.delete_node("planner-2")
        assert isinstance(result, Ok)
        head = next(n for n in result.value.nodes if n.id == "planner")
        assert head.edges == ()
        assert app._cursor == "planner"


@pytest.mark.asyncio
async def test_deleting_the_entry_node_reassigns_entry(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:planner")  # planner (entry)
        app.add_node_from_card("agent:planner")  # planner-2

        result = app.delete_node("planner")
        assert isinstance(result, Ok)
        assert result.value.entry == "planner-2"
        assert app._cursor == "planner-2"


@pytest.mark.asyncio
async def test_deleting_the_last_node_clears_the_cursor(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:planner")

        result = app.delete_node("planner")
        assert isinstance(result, Ok)
        assert result.value.node_ids == ()
        assert app._cursor is None


@pytest.mark.asyncio
async def test_app_boots_headless_without_error(tmp_path: Path) -> None:
    claude_root, flows_dir = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=flows_dir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(AgentCards) is not None
        assert app.query_one(FlowsPanel) is not None
