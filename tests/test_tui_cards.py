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
from textual.css.query import NoMatches
from textual.widgets import Input, Select, Static

from tui.app import AgentCards, BranchEditor, DeVinciApp, GraphBuilderPanel, NameEditor


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
        roots=(_seed(tmp_path),),
        flows_dir=tmp_path / "flows",
        graphs_dir=tmp_path / "graphs",
        runner=FakeRunner(),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        app.add_node_from_card("agent:reviewer")
        report = await app.run_builder()
        assert isinstance(report, Ok)
        assert report.value.statuses.get("coder") is NodeStatus.SUCCEEDED
        # x is save + execute: the graph YAML is persisted before it runs.
        assert (tmp_path / "graphs" / "draft.yaml").exists()


@pytest.mark.asyncio
async def test_run_empty_builder_is_err(tmp_path: Path) -> None:
    app = DeVinciApp(
        roots=(_seed(tmp_path),),
        flows_dir=tmp_path / "flows",
        graphs_dir=tmp_path / "graphs",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(await app.run_builder(), Err)
        # An unbuildable canvas is never persisted.
        assert not (tmp_path / "graphs").exists()


class _FallbackGraphWriter:
    """Graph command writer that always defers to the deterministic orchestration."""

    def write(self, graph, *, command_name):  # type: ignore[no-untyped-def]
        return Err("no draft")


@pytest.mark.asyncio
async def test_save_builder_persists_graph_and_exports_command(tmp_path: Path) -> None:
    claude_root = _seed(tmp_path)
    app = DeVinciApp(
        roots=(claude_root,),
        flows_dir=tmp_path / "flows",
        graphs_dir=tmp_path / "graphs",
        graph_command_writer=_FallbackGraphWriter(),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        app.add_node_from_card("agent:reviewer")

        result = await app.save_builder()

        assert isinstance(result, Ok)
        assert (tmp_path / "graphs" / "draft.yaml").exists()
        command = claude_root / "commands" / "draft.md"
        assert command.exists()
        text = command.read_text(encoding="utf-8")
        # Self-contained orchestration naming both agents; no runtime shim.
        assert "agent:coder" in text
        assert "agent:reviewer" in text
        assert "--run-graph" not in text


@pytest.mark.asyncio
async def test_save_prompts_for_name_and_uses_chosen_name(tmp_path: Path) -> None:
    claude_root = _seed(tmp_path)
    app = DeVinciApp(
        roots=(claude_root,),
        flows_dir=tmp_path / "flows",
        graphs_dir=tmp_path / "graphs",
        graph_command_writer=_FallbackGraphWriter(),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")
        app.add_node_from_card("agent:reviewer")

        app.action_save_builder()  # opens the NameEditor modal
        await pilot.pause()
        assert isinstance(app.screen, NameEditor)
        app.screen.query_one("#name", Input).value = "ship"
        await pilot.click("#save")
        await app.workers.wait_for_complete()
        await pilot.pause()

        # The chosen name — not the "draft" default — names both artifacts.
        assert (tmp_path / "graphs" / "ship.yaml").exists()
        assert (claude_root / "commands" / "ship.md").exists()
        assert not (tmp_path / "graphs" / "draft.yaml").exists()
        assert app._builder.name == "ship"


@pytest.mark.asyncio
async def test_save_cancelled_name_writes_nothing(tmp_path: Path) -> None:
    claude_root = _seed(tmp_path)
    app = DeVinciApp(
        roots=(claude_root,),
        flows_dir=tmp_path / "flows",
        graphs_dir=tmp_path / "graphs",
        graph_command_writer=_FallbackGraphWriter(),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:coder")

        app.action_save_builder()
        await pilot.pause()
        assert isinstance(app.screen, NameEditor)
        await pilot.press("escape")  # cancel the NameEditor
        await app.workers.wait_for_complete()
        await pilot.pause()

        # Nothing persisted, and the builder name is left at its default.
        assert not (tmp_path / "graphs").exists() or not any(
            (tmp_path / "graphs").iterdir()
        )
        assert app._builder.name == "draft"


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


@pytest.mark.asyncio
async def test_agent_added_after_if_else_chains_from_the_else_card_and_renders(
    tmp_path: Path,
) -> None:
    """Regression: adding an agent right after creating an if/else used to raise
    the node count with nothing new on the blueprint canvas — the renderer
    stopped drawing at the fork entirely (see tui/blueprint.py). The cursor
    lands on the else card after if/else, so the next card-add must chain from
    it *and* actually show up in the rendered panel.
    """
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        result = app.add_if_else_cards(
            "reviewer",
            condition="review passes",
            if_ref="agent:coder",
            else_ref="agent:reviewer",
        )
        assert isinstance(result, Ok)
        assert app._cursor == "reviewer-2"  # the else card

        added = app.add_node_from_card("agent:coder")
        assert isinstance(added, Ok)
        builder = added.value
        assert builder.node_ids == ("reviewer", "coder", "reviewer-2", "coder-2")

        # chained from the else card, not left dangling.
        else_card = next(n for n in builder.nodes if n.id == "reviewer-2")
        assert [e.to for e in else_card.edges] == ["coder-2"]

        # and it's on the canvas, not just in the node count.
        panel = app.query_one(GraphBuilderPanel)
        rendered = _plain(panel._build(builder, {}))
        assert "coder-2" in rendered


@pytest.mark.asyncio
async def test_flip_branch_key_redirects_the_next_add_to_the_if_card(
    tmp_path: Path,
) -> None:
    """Regression: after creating if/else the cursor always lands on the else
    card, so every follow-up add kept stretching only the else branch with no
    quick way to redirect — the reported complaint. 'f' must jump the cursor to
    the if card so the next add chains from *it* instead.
    """
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        result = app.add_if_else_cards(
            "reviewer",
            condition="review passes",
            if_ref="agent:coder",
            else_ref="agent:reviewer",
        )
        assert isinstance(result, Ok)
        assert app._cursor == "reviewer-2"  # else, by default

        app.action_flip_branch()
        assert app._cursor == "coder"  # jumped to the if card

        # flipping again, before adding anything, goes straight back to else.
        app.action_flip_branch()
        assert app._cursor == "reviewer-2"

        # flip back to if and stay there for the actual add.
        app.action_flip_branch()
        assert app._cursor == "coder"

        added = app.add_node_from_card("agent:coder")
        assert isinstance(added, Ok)
        builder = added.value
        assert builder.node_ids == ("reviewer", "coder", "reviewer-2", "coder-2")

        # chained from the if card this time, else card untouched.
        if_card = next(n for n in builder.nodes if n.id == "coder")
        else_card = next(n for n in builder.nodes if n.id == "reviewer-2")
        assert [e.to for e in if_card.edges] == ["coder-2"]
        assert else_card.edges == ()

        # and it renders in the (if) band, not just the node count.
        panel = app.query_one(GraphBuilderPanel)
        rendered = _plain(panel._build(builder, {}, cursor="coder"))
        assert "coder-2" in rendered
        assert "(if card — f to flip)" in rendered


@pytest.mark.asyncio
async def test_flip_branch_on_a_non_branch_cursor_warns_and_stays_put(
    tmp_path: Path,
) -> None:
    app = DeVinciApp(roots=(_seed(tmp_path),), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        assert app._cursor == "reviewer"

        app.action_flip_branch()
        assert app._cursor == "reviewer"  # unchanged — not a branch card


@pytest.mark.asyncio
async def test_branch_key_mounts_editor_with_every_catalog_kind(tmp_path: Path) -> None:
    """Regression: the 'b' binding (action_branch_node) must actually mount
    BranchEditor without crashing, and its IF/ELSE pickers must offer agents,
    skills, and commands alike — not just agents. (The mount path is what a
    direct `add_if_else_cards()` call in other tests skips, so it's the only
    way to catch a widget-mounting bug here — this is exactly how a prior
    revision shadowed Textual's own `Widget._nodes` attribute and crashed on
    press.)
    """
    claude_root = _seed(tmp_path)
    (claude_root / "commands").mkdir(parents=True)
    (claude_root / "commands" / "release.md").write_text(
        "---\nname: release\ndescription: ships the build\n---\nbody\n"
    )
    app = DeVinciApp(roots=(claude_root,), flows_dir=tmp_path / "flows")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.add_node_from_card("agent:reviewer")
        await pilot.pause()

        app.action_branch_node()
        await pilot.pause()

        editor = app.screen
        assert isinstance(editor, BranchEditor)

        # both branches were built from the same widened catalog (agent + command
        # here; skills would join too if _seed grew one) — not agent-only.
        kinds = {node.kind.value for node in editor._choices}
        assert kinds == {"agent", "command"}

        # IF and ELSE pickers share that exact set (symmetric, per the request).
        assert editor.query_one("#if-agent", Select) is not None
        assert editor.query_one("#else-agent", Select) is not None

        # tools readout is present and populated for the initial selection.
        assert editor.query_one("#if-tools", Static) is not None
        assert editor.query_one("#else-tools", Static) is not None
        first_key = next(iter(editor._by_key))
        assert editor._tools_line(first_key).startswith("tools:")

        # the free-text "card text" fields were deliberately dropped.
        with pytest.raises(NoMatches):
            editor.query_one("#if-text", Input)
        with pytest.raises(NoMatches):
            editor.query_one("#else-text", Input)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, BranchEditor)


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
