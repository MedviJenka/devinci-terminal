"""Agent cards + interactive graph building in the terminal.

The PALETTE is now a grid of selectable agent cards. Selecting a card creates a
graph node (auto-chained from the previous one); a wire command adds branch/loop
edges; the GraphBuilderPanel renders the graph-under-construction via the blueprint
renderer; and editing a card rewrites its .claude definition on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.result import Err, Ok
from discovery import NodeKind, scan
from flows import EdgeKind, NodeStatus
from tests.test_tui_app import _plain
from tui.app import AgentCards, DeVinciApp, GraphBuilderPanel


def _seed(tmp_path: Path) -> Path:
    claude_root = tmp_path / ".claude"
    (claude_root / "agents").mkdir(parents=True)
    (claude_root / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: reviews the diff\n"
        "tools:\n  - Read\n  - Grep\nmodel: opus\n---\nbody\n"
    )
    (claude_root / "agents" / "coder.md").write_text(
        "---\nname: coder\ndescription: writes the code\n---\nbody\n"
    )
    return claude_root


# --- cards render -----------------------------------------------------------


def test_agent_card_shows_name_description_and_meta(tmp_path: Path) -> None:
    catalog = scan((_seed(tmp_path),))
    node = catalog.find(NodeKind.AGENT, "reviewer")
    assert node is not None
    rendered = _plain(AgentCards()._card(node))
    assert "reviewer" in rendered
    assert "reviews the diff" in rendered
    assert "Read" in rendered and "opus" in rendered


def test_graph_builder_panel_placeholder_when_empty() -> None:
    rendered = _plain(GraphBuilderPanel()._build(None, {}))
    assert "card" in rendered.lower()  # hint mentions picking cards


@pytest.mark.asyncio
async def test_agents_panel_is_visible_on_a_small_terminal(tmp_path: Path) -> None:
    # Regression: the layout once stacked so much that #panels overflowed off the
    # top of an 80x24 terminal and AgentCards collapsed to height 0 — options were
    # present but nothing was on screen. Guard that the panel keeps real height.
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        cards = app.query_one(AgentCards)
        assert cards.option_count >= 2  # both seeded agents catalogued
        assert cards.size.height > 0  # …and the panel is actually on screen
        builder = app.query_one(GraphBuilderPanel)
        assert builder.border_title == "FLOW BLUEPRINT"
        assert app.screen.children[0].region.y >= 0  # banner not pushed off top


# --- node creation ----------------------------------------------------------


@pytest.mark.asyncio
async def test_selecting_cards_creates_and_chains_nodes(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.add_node_from_card("agent:coder"), Ok)
        assert isinstance(app.add_node_from_card("agent:reviewer"), Ok)

        builder = app._builder
        assert builder.node_ids == ("coder", "reviewer")
        assert builder.entry == "coder"
        # auto-chained: coder → reviewer
        coder = builder.build().value.by_id("coder")
        assert coder is not None
        assert coder.edges[0].to == "reviewer"


@pytest.mark.asyncio
async def test_add_unknown_card_is_err(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.add_node_from_card("agent:ghost"), Err)


@pytest.mark.asyncio
async def test_wire_command_adds_a_branch_edge(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        app.add_node_from_card("agent:coder")
        result = app.apply_wire("reviewer false> coder needs work")
        assert isinstance(result, Ok)

        # Inspect the builder directly — the ON_FALSE edge landed on 'reviewer'.
        reviewer = next(n for n in app._builder.nodes if n.id == "reviewer")
        false_edges = [e for e in reviewer.edges if e.kind is EdgeKind.ON_FALSE]
        assert false_edges and false_edges[0].to == "coder"
        assert false_edges[0].condition == "needs work"


# --- editing a card rewrites the definition ---------------------------------


@pytest.mark.asyncio
async def test_edit_agent_rewrites_the_definition_file(tmp_path: Path) -> None:
    claude_root = _seed(tmp_path)
    app = DeVinciApp(roots=(claude_root,), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        node = app._catalog.find(NodeKind.AGENT, "reviewer")
        assert node is not None

        result = app.edit_agent(
            node, description="reviews for bugs and security", tools=("Read", "Bash"), model="sonnet"
        )
        assert isinstance(result, Ok)

        # Re-scan from disk proves the edit persisted.
        rescanned = scan((claude_root,)).find(NodeKind.AGENT, "reviewer")
        assert rescanned is not None
        assert rescanned.description == "reviews for bugs and security"
        assert rescanned.tools == ("Read", "Bash")
        assert rescanned.model == "sonnet"


# --- building + running a hand-made graph -----------------------------------


@pytest.mark.asyncio
async def test_run_builder_executes_the_built_graph(tmp_path: Path) -> None:
    from common.result import Result
    from discovery import CatalogNode

    class FakeRunner:
        def run(self, node: CatalogNode, inputs: str) -> Result[str, str]:
            return Ok(f"out:{node.name}")

    app = DeVinciApp(
        roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows", runner=FakeRunner()
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        app.add_node_from_card("agent:reviewer")
        report = await app.run_builder()
        assert isinstance(report, Ok)
        assert report.value.statuses.get("coder") is NodeStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_run_empty_builder_is_err(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(await app.run_builder(), Err)


# --- keyboard canvas: cursor, repeat, branch --------------------------------


@pytest.mark.asyncio
async def test_new_node_connects_from_cursor_and_advances_it(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        assert app._cursor == "coder"  # first node becomes the cursor
        app.add_node_from_card("agent:reviewer")
        assert app._cursor == "reviewer"  # cursor advances to the newest node


@pytest.mark.asyncio
async def test_set_cursor_lets_you_branch_from_an_earlier_node(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        app.add_node_from_card("agent:coder")
        assert isinstance(app.set_cursor("reviewer"), Ok)
        assert app._cursor == "reviewer"
        assert isinstance(app.set_cursor("ghost"), Err)


@pytest.mark.asyncio
async def test_set_node_repeat_via_app(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        result = app.set_node_repeat("coder", 4)
        assert isinstance(result, Ok)
        node = next(n for n in app._builder.nodes if n.id == "coder")
        assert node.repeat == 4


@pytest.mark.asyncio
async def test_make_branch_via_app_builds_a_conditional(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        app.add_node_from_card("agent:coder")  # reviewer -> coder (NEXT)
        result = app.make_branch("reviewer", "coder", "reviewer", "looks good")
        assert isinstance(result, Ok)

        review = app._builder.build()
        # reviewer now branches: true->coder, false->reviewer (self-loop bounded by max_visits)
        assert isinstance(review, Ok)
        node = next(n for n in review.value.nodes if n.id == "reviewer")
        kinds = {e.kind for e in node.edges}
        assert EdgeKind.ON_TRUE in kinds and EdgeKind.ON_FALSE in kinds



@pytest.mark.asyncio
async def test_if_else_action_creates_branch_cards_from_agent_choices(
    tmp_path: Path,
) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        result = app.add_if_else_cards(
            "reviewer",
            condition="review passes",
            if_ref="agent:coder",
            else_ref="agent:reviewer",
            if_text="if approved",
            else_text="else revise",
            if_prompt="implement the approved change",
            else_prompt="explain why it failed",
        )
        assert isinstance(result, Ok)

        builder = result.value
        assert builder.node_ids == ("reviewer", "coder", "reviewer-2")
        reviewer = next(n for n in builder.nodes if n.id == "reviewer")
        by_kind = {e.kind: e for e in reviewer.edges}
        assert by_kind[EdgeKind.ON_TRUE].to == "coder"
        assert by_kind[EdgeKind.ON_FALSE].to == "reviewer-2"
        assert by_kind[EdgeKind.ON_TRUE].condition == "review passes"
        assert builder.nodes[1].text == "if approved"
        assert builder.nodes[1].prompt == "implement the approved change"
        assert builder.nodes[2].text == "else revise"
        assert builder.nodes[2].prompt == "explain why it failed"


@pytest.mark.asyncio
async def test_adding_after_a_branch_node_adds_no_dead_next_edge(tmp_path: Path) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        app.add_node_from_card("agent:coder")
        app.make_branch("reviewer", "coder", "reviewer", "ok")  # reviewer is now if/else
        app.set_cursor("reviewer")
        app.add_node_from_card("agent:coder")  # coder-2, cursor on a conditional node

        reviewer = next(n for n in app._builder.nodes if n.id == "reviewer")
        # No stray NEXT edge — the interpreter would ignore it, orphaning coder-2.
        assert all(e.kind is not EdgeKind.NEXT for e in reviewer.edges)
