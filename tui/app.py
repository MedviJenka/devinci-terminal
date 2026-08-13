"""DeVinci — the orchestration terminal (Textual).

The screen: an animated oh-my-pi gradient banner over the PALETTE (nodes
discovered from .claude) and FLOWS (saved, selectable pipelines), a live RunPanel
that lights each node green/red as a flow executes, and a goal input that designs
a brand-new flow from a natural-language description. It reads real data, not a
mock. Two verbs: type a goal to *create* a flow; select a flow to *run* it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from common.result import Err, Ok, Result
from discovery import Catalog, CatalogNode, NodeKind, scan, write_node
from flows import (
    Completion,
    EdgeKind,
    Flow,
    Graph,
    GraphBuilder,
    GraphReport,
    NodeEvent,
    NodeStatus,
    RunReport,
    author_flow,
    execute,
    list_flows,
    run_graph,
    save,
    save_graph,
)
from flows.commands import (
    CrewAICommandWriter,
    CrewAIGraphCommandWriter,
    FlowCommandWriter,
    GraphCommandWriter,
    write_flow_command,
    write_graph_command,
)
from runtime import ClaudeCodeCompletion, ClaudeCodeRunner, ClaudeCondition, Condition, NodeRunner
from tui.blueprint import render_blueprint
from tui.theme import OH_MY_PI, gradient_text, hex_of
from tui.wire import parse_wire

__all__ = [
    "DeVinciApp",
    "AgentCards",
    "GraphBuilderPanel",
    "CardEditor",
    "RepeatEditor",
    "BranchEditor",
    "RunPanel",
    "run",
]

_BANNER = "◆ DeVinci"
_SUBTITLE = "orchestration terminal · design · save · run reusable flows"

# Glyph + palette colour for each node status in the run view.
_RUN_STYLE: dict[NodeStatus, tuple[str, tuple[int, int, int]]] = {
    NodeStatus.RUNNING: ("◐", OH_MY_PI["amber"]),
    NodeStatus.SUCCEEDED: ("●", OH_MY_PI["lime"]),
    NodeStatus.FAILED: ("✗", OH_MY_PI["red"]),
    NodeStatus.SKIPPED: ("◌", OH_MY_PI["slate"]),
}
_PENDING_STYLE: tuple[str, tuple[int, int, int]] = ("◌", OH_MY_PI["slate"])


def _truncate(text: str, limit: int) -> str:
    """Single-line preview of `text`, ellipsised past `limit` chars."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"



@dataclass(frozen=True, slots=True)
class IfElseSpec:
    """Editor payload for creating two inline if/else branch cards."""

    condition: str
    if_ref: str
    else_ref: str
    if_text: str = ""
    else_text: str = ""
    if_prompt: str = ""
    else_prompt: str = ""


def _default_roots() -> tuple[Path, ...]:
    """The .claude roots to discover nodes from: project first, then user-global."""
    return (Path.cwd() / ".claude", Path.home() / ".claude")


def _default_flows_dir() -> Path:
    return Path.cwd() / ".devinci" / "flows"


def _default_graphs_dir() -> Path:
    return Path.cwd() / ".devinci" / "graphs"


class Banner(Static):
    """Full-width gradient wordmark that shimmers by advancing the phase."""

    phase: reactive[float] = reactive(0.0)

    def on_mount(self) -> None:
        # ~12 fps shimmer; small enough to be smooth, cheap enough to idle.
        self.set_interval(1 / 12, self._advance)

    def _advance(self) -> None:
        self.phase = (self.phase + 0.012) % 1.0

    def watch_phase(self, phase: float) -> None:
        title = gradient_text(_BANNER, phase=phase, bold=True)
        subtitle = Text(_SUBTITLE, style=hex_of(OH_MY_PI["slate"]))
        self.update(Group(title, subtitle))


class AgentCards(OptionList):
    """The discovered agents as selectable cards — the graph-building palette.

    Each option is a card showing the agent's name, description, and tools/model.
    Selecting a card adds it to the graph under construction (see the app handler).
    """

    def show(self, catalog: Catalog) -> None:
        self.clear_options()
        agents = catalog.of_kind(NodeKind.AGENT)
        if not agents:
            self.add_option(
                Option(
                    Text("no agents discovered under .claude/agents", style="dim italic"),
                    disabled=True,
                )
            )
            return
        for node in agents:
            self.add_option(Option(self._card(node), id=node.key))

    def _card(self, node: CatalogNode) -> Group:
        # Compact two-line card: name + meta on the header, description below.
        # Two lines (not three) so more agents stay visible on short terminals.
        header = gradient_text(
            node.name, stops=(OH_MY_PI["cyan"], OH_MY_PI["violet"]), bold=True
        )
        if node.tools:
            header.append(f"  {', '.join(node.tools[:3])}", style=hex_of(OH_MY_PI["slate"]))
        if node.model:
            header.append(f"  ▸ {node.model}", style=hex_of(OH_MY_PI["amber"]))
        desc = Text(_truncate(node.description, 56), style="dim")
        return Group(header, desc)


class FlowsPanel(OptionList):
    """The saved, reusable pipelines — selectable; Enter runs the highlighted flow."""

    def show(self, flows: tuple[Flow, ...]) -> None:
        self.clear_options()
        if not flows:
            self.add_option(
                Option(
                    Text(
                        "no saved flows yet — describe one below to create it",
                        style="dim italic",
                    ),
                    disabled=True,
                )
            )
            return
        for flow in flows:
            self.add_option(Option(self._row(flow), id=flow.name))

    def _row(self, flow: Flow) -> Text:
        line = gradient_text(
            flow.name, stops=(OH_MY_PI["lime"], OH_MY_PI["amber"]), bold=True
        )
        line.append(f"  · {len(flow.nodes)} steps", style="dim")
        return line


class RunPanel(Static):
    """Live execution status: one row per node, lit by its current status."""

    def show(self, flow: Flow | None, statuses: dict[str, NodeStatus]) -> None:
        self.update(self._build(flow, statuses))

    def _build(self, flow: Flow | None, statuses: dict[str, NodeStatus]) -> Group:
        if flow is None:
            return Group(Text("select a flow above to run it (Enter)", style="dim italic"))
        table = Table.grid(padding=(0, 1))
        for _ in range(4):
            table.add_column()
        for node in flow.nodes:
            status = statuses.get(node.id)
            glyph, color = _RUN_STYLE.get(status, _PENDING_STYLE)
            label = status.value if status else "pending"
            table.add_row(
                Text(glyph, style=hex_of(color) + " bold"),
                Text(node.id, style=hex_of(color) + " bold"),
                Text(node.ref, style="dim"),
                Text(label, style=hex_of(color)),
            )
        return Group(table)


class GraphBuilderPanel(Static):
    """The control-flow graph being assembled by hand from agent cards."""

    def show(
        self,
        builder: GraphBuilder | None,
        statuses: dict[str, NodeStatus],
        cursor: str | None = None,
    ) -> None:
        self.update(self._build(builder, statuses, cursor))

    def _build(
        self,
        builder: GraphBuilder | None,
        statuses: dict[str, NodeStatus],
        cursor: str | None = None,
    ) -> Group:
        if builder is None or not builder.nodes:
            return Group(
                Text(
                    "pick an agent card (Enter) to add a node · [ ] move cursor · "
                    "l loop ×N · b if/else · s save+export · x save+run",
                    style="dim italic",
                )
            )
        display = Graph(
            name=builder.name,
            description=builder.description,
            entry=builder.entry,
            nodes=builder.nodes,
        )
        header = Text("current ▸ ", style="dim")
        header.append(cursor or "—", style=hex_of(OH_MY_PI["pink"]) + " bold")
        return Group(header, render_blueprint(display, statuses))


class CardEditor(ModalScreen[CatalogNode | None]):
    """Modal form to edit an agent's definition; dismisses with the edited node."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, node: CatalogNode) -> None:
        super().__init__()
        self._node = node

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Label(f"Edit agent: {self._node.name}")
            yield Input(self._node.description, placeholder="description", id="desc")
            yield Input(", ".join(self._node.tools), placeholder="tools (comma)", id="tools")
            yield Input(self._node.model or "", placeholder="model (optional)", id="model")
            with Horizontal(id="editor-buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def _edited(self) -> CatalogNode:
        desc = self.query_one("#desc", Input).value.strip()
        tools = tuple(
            t.strip() for t in self.query_one("#tools", Input).value.split(",") if t.strip()
        )
        model = self.query_one("#model", Input).value.strip() or None
        return replace(self._node, description=desc, tools=tools, model=model)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._edited() if event.button.id == "save" else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class RepeatEditor(ModalScreen[int | None]):
    """Ask how many times a node should run in place; dismiss with the count."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, node_id: str, current: int) -> None:
        super().__init__()
        self._node_id = node_id
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Label(f"Loop '{self._node_id}' — run how many times?")
            yield Input(str(self._current), placeholder="count (≥ 1)", id="count")
            with Horizontal(id="editor-buttons"):
                yield Button("Set", variant="primary", id="set")
                yield Button("Cancel", id="cancel")

    def _count(self) -> int | None:
        raw = self.query_one("#count", Input).value.strip()
        return int(raw) if raw.isdigit() and int(raw) >= 1 else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._count() if event.button.id == "set" else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class NameEditor(ModalScreen[str | None]):
    """Ask what to name the graph on save; dismiss with the chosen name.

    The name becomes both the graph's YAML filename and its `/<name>` slash
    command, so an empty name is refused rather than dismissed to a blank.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Label("Save graph as — this names its /command too")
            yield Input(self._current, placeholder="name (e.g. ship)", id="name")
            with Horizontal(id="editor-buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def _chosen(self) -> str | None:
        raw = self.query_one("#name", Input).value.strip()
        return raw or None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._chosen() if event.button.id == "save" else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter in the field confirms, matching the primary "Save" button.
        event.stop()
        self.dismiss(self._chosen())

    def action_cancel(self) -> None:
        self.dismiss(None)


class BranchEditor(ModalScreen[IfElseSpec | None]):
    """Create if/else cards: each branch chooses an agent and optional prompt."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, node_id: str, agents: tuple[CatalogNode, ...]) -> None:
        super().__init__()
        self._node_id = node_id
        self._agents = agents

    def compose(self) -> ComposeResult:
        options = [(node.name, node.key) for node in self._agents]
        first = options[0][1]
        with Vertical(id="editor"):
            yield Label(f"If/else after '{self._node_id}'")
            yield Input(placeholder="condition text, e.g. 'tests passed'", id="cond")
            yield Input(placeholder="IF card text", id="if-text")
            yield Select(options, prompt="IF agent", allow_blank=False, value=first, id="if-agent")
            yield Input(placeholder="IF prompt (optional)", id="if-prompt")
            yield Input(placeholder="ELSE card text", id="else-text")
            yield Select(
                options, prompt="ELSE agent", allow_blank=False, value=first, id="else-agent"
            )
            yield Input(placeholder="ELSE prompt (optional)", id="else-prompt")
            with Horizontal(id="editor-buttons"):
                yield Button("Create cards", variant="primary", id="wire")
                yield Button("Cancel", id="cancel")

    def _spec(self) -> IfElseSpec | None:
        if_ref = self.query_one("#if-agent", Select).value
        else_ref = self.query_one("#else-agent", Select).value
        if not isinstance(if_ref, str) or not isinstance(else_ref, str):
            return None
        return IfElseSpec(
            condition=self.query_one("#cond", Input).value.strip(),
            if_ref=if_ref,
            else_ref=else_ref,
            if_text=self.query_one("#if-text", Input).value.strip(),
            else_text=self.query_one("#else-text", Input).value.strip(),
            if_prompt=self.query_one("#if-prompt", Input).value.strip(),
            else_prompt=self.query_one("#else-prompt", Input).value.strip(),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._spec() if event.button.id == "wire" else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DeVinciApp(App[None]):
    """DeVinci orchestration terminal."""

    CSS = """
    /* ── Design tokens ─────────────────────────────────────────────
       Primitives → semantic roles. Each region owns an oh-my-pi accent
       so the eye maps colour → purpose at a glance (mirrors _RUN_STYLE
       and tui.theme.OH_MY_PI). Change a colour here, not per-rule. */
    $surface:   #0b0f19;   /* screen base                */
    $panel:     #101628;   /* raised panel body          */
    $panel-a:   #10162899; /* raised panel, translucent  */
    $muted:     #94a3b8;   /* slate — secondary text     */
    $agents:    #4adeff;   /* cyan                       */
    $flows:     #a3e635;   /* lime                       */
    $blueprint: #ec4899;   /* pink                       */
    $run:       #fbbf24;   /* amber                      */
    $goal:      #a855f7;   /* violet                     */

    Screen { background: $surface; }
    Banner { height: 3; padding: 1 2 0 2; content-align: left middle; }
    /* The two flexible regions must SHRINK to fit the terminal, or the top
       (agents) overflows off-screen. No min-heights (they force overflow); fr
       weights give the picking panels the larger share, the canvas the rest, and
       RunPanel stays a small auto strip that only grows while a flow runs. */
    #panels { height: 3fr; padding: 1 2; }

    /* Picking panels share a shape and differ only by accent. The border sits
       dim at rest and lifts to full accent on focus, so the panel receiving
       keystrokes is unmistakable — feedback, not decoration. */
    AgentCards, FlowsPanel {
        width: 1fr; height: 1fr; margin: 0 1;
        border: round $agents 55%; padding: 1 2; background: $panel-a;
        border-title-color: $agents; border-title-style: bold; border-title-align: left;
    }
    FlowsPanel { border: round $flows 55%; border-title-color: $flows; }
    AgentCards:focus { border: round $agents; background: $panel; }
    FlowsPanel:focus { border: round $flows; background: $panel; }

    /* The highlighted/hovered row reads in the panel's own accent so the
       current pick is obvious in a keyboard-driven list. */
    AgentCards > .option-list--option-highlighted {
        background: $agents 20%; color: $agents; text-style: bold;
    }
    AgentCards > .option-list--option-hover { background: $agents 12%; }
    FlowsPanel > .option-list--option-highlighted {
        background: $flows 20%; color: $flows; text-style: bold;
    }
    FlowsPanel > .option-list--option-hover { background: $flows 12%; }

    GraphBuilderPanel {
        height: 1fr; margin: 0 3; overflow-y: auto;
        border: round $blueprint; padding: 0 2; background: $panel;
        border-title-color: $blueprint; border-title-style: bold; border-title-align: left;
        scrollbar-size-vertical: 1;
        scrollbar-color: $blueprint 60%; scrollbar-color-hover: $blueprint;
        scrollbar-color-active: $blueprint; scrollbar-background: $panel;
    }
    RunPanel {
        height: auto; max-height: 6; margin: 0 3 1 3;
        border: round $run; padding: 0 2; background: $panel;
        border-title-color: $run; border-title-style: bold; border-title-align: left;
    }
    #goal {
        margin: 0 3 1 3; border: round $goal 70%; background: $panel;
    }
    #goal:focus { border: round $blueprint; }
    #goal > .input--placeholder { color: $muted; }

    CardEditor { align: center middle; }
    #editor {
        width: 70; height: auto; padding: 1 2;
        border: round $goal; background: $panel;
        border-title-color: $goal; border-title-style: bold;
    }
    #editor Input { margin: 1 0; border: round $goal 55%; }
    #editor Input:focus { border: round $goal; }
    #editor-buttons { height: auto; align: right middle; }
    #editor-buttons Button { margin: 0 1; }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("e", "edit_agent", "Edit card"),
        ("left_square_bracket", "cursor_prev", "◂ node"),
        ("right_square_bracket", "cursor_next", "node ▸"),
        ("l", "loop_node", "Loop ×N"),
        ("b", "branch_node", "If/else"),
        ("d", "delete_node", "Delete node"),
        ("s", "save_builder", "Save + export"),
        ("x", "run_builder", "Save + run"),
        ("c", "clear_builder", "Clear graph"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        roots: tuple[Path, ...] | None = None,
        flows_dir: Path | None = None,
        graphs_dir: Path | None = None,
        completion: Completion | None = None,
        runner: NodeRunner | None = None,
        condition: Condition | None = None,
        command_writer: FlowCommandWriter | None = None,
        graph_command_writer: GraphCommandWriter | None = None,
        run_created_flow: bool = False,
    ) -> None:
        super().__init__()
        self._roots = roots if roots is not None else _default_roots()
        self._flows_dir = flows_dir if flows_dir is not None else _default_flows_dir()
        self._graphs_dir = graphs_dir if graphs_dir is not None else _default_graphs_dir()
        self._completion = completion if completion is not None else ClaudeCodeCompletion()
        self._runner = runner if runner is not None else ClaudeCodeRunner(self._completion)
        self._condition = condition if condition is not None else ClaudeCondition(self._completion)
        self._command_writer = (
            command_writer if command_writer is not None else CrewAICommandWriter()
        )
        self._graph_command_writer = (
            graph_command_writer if graph_command_writer is not None
            else CrewAIGraphCommandWriter()
        )
        self._run_created_flow = run_created_flow
        self._catalog = Catalog()
        self._flows: dict[str, Flow] = {}
        self._current_flow: Flow | None = None
        self._run_status: dict[str, NodeStatus] = {}
        self._builder = GraphBuilder(name="draft", description="hand-built in the terminal")
        self._builder_status: dict[str, NodeStatus] = {}
        self._cursor: str | None = None

    def compose(self) -> ComposeResult:
        yield Banner()
        with Horizontal(id="panels"):
            yield AgentCards()
            yield FlowsPanel()
        yield GraphBuilderPanel(id="builder")
        yield RunPanel(id="run")
        yield Input(
            placeholder="Describe a flow to create — e.g. 'review a PR and fix issues'",
            id="goal",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(AgentCards).border_title = "AGENTS ▸ pick to add a node"
        self.query_one(FlowsPanel).border_title = "FLOWS"
        self.query_one(GraphBuilderPanel).border_title = "FLOW BLUEPRINT"
        self.query_one(RunPanel).border_title = "RUN"
        self.action_refresh()

    def action_refresh(self) -> None:
        self._catalog = scan(self._roots)
        flows = list_flows(self._flows_dir)
        self._flows = {flow.name: flow for flow in flows}
        self.query_one(AgentCards).show(self._catalog)
        self.query_one(FlowsPanel).show(flows)
        self._render_run()
        self._render_builder()

    # --- create a flow -----------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Only the goal input authors a flow; ignore submits bubbling from the
        # modal editors' own Input fields.
        if event.input.id != "goal":
            return
        goal = event.value.strip()
        if not goal:
            return
        event.input.value = ""
        self.notify(f"Designing a flow for: {goal} …")
        self._author_worker(goal)

    @work(exclusive=True)
    async def _author_worker(self, goal: str) -> None:
        result = await self.author_and_save(goal)
        if isinstance(result, Err):
            self.notify(result.error, title="Authoring failed", severity="error")
            return
        flow = result.value
        self.notify(f"Saved flow '{flow.name}' ({len(flow.nodes)} steps)")
        self.action_refresh()

    async def author_and_save(self, goal: str) -> Result[Flow, str]:
        """Design a flow, persist it, emit a Claude command, and optionally run it.

        Authoring is synchronous (the model call blocks), so it is offloaded to a
        thread to keep the UI responsive. Command Markdown is generated after the
        flow YAML exists so the slash command can run the saved flow by name.
        """
        goal = goal.strip()
        if not goal:
            return Err("goal must not be empty")

        authored = await asyncio.to_thread(
            author_flow, goal, self._catalog, self._completion
        )
        if isinstance(authored, Err):
            return authored

        saved = save(authored.value, self._flows_dir)
        if isinstance(saved, Err):
            return saved

        command = write_flow_command(
            authored.value,
            self._commands_dir(),
            flows_dir=self._flows_dir,
            writer=self._command_writer,
        )
        if isinstance(command, Err):
            return command

        if self._run_created_flow:
            run = await self.run_flow(authored.value)
            if isinstance(run, Err):
                return run
        return Ok(authored.value)

    def _commands_dir(self) -> Path:
        root = self._roots[0] if self._roots else Path.cwd() / ".claude"
        return root / "commands"

    # --- build a graph from cards -----------------------------------------

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected = event.option.id
        if not selected:
            return
        if isinstance(event.option_list, AgentCards):
            result = self.add_node_from_card(selected)
            if isinstance(result, Err):
                self.notify(result.error, title="Add node failed", severity="error")
            return
        self._run_worker(selected)

    def add_node_from_card(self, key: str) -> Result[GraphBuilder, str]:
        """Add the agent `key` as a node, connecting it from the current cursor.

        The cursor is the node new work attaches to: the added node gets a NEXT edge
        from it, then the cursor advances to the new node. Move the cursor ([ / ])
        to branch or chain from an earlier node instead of the newest one.
        """
        node = next((n for n in self._catalog.nodes if n.key == key), None)
        if node is None:
            return Err(f"no catalog node '{key}'")

        added = self._builder.add_node(key)
        if isinstance(added, Err):
            return added
        builder = added.value
        new_id = builder.node_ids[-1]

        if self._cursor is not None and not self._is_conditional(self._cursor):
            # Chain from the cursor with a NEXT edge — but not off an if/else node,
            # whose routing is decided by its ON_TRUE/ON_FALSE branches (a NEXT edge
            # there is dead weight the interpreter ignores). Both ids exist, so this
            # connect cannot fail.
            chained = builder.connect(self._cursor, new_id)
            if isinstance(chained, Ok):
                builder = chained.value

        self._builder = builder
        self._builder_status = {}
        self._cursor = new_id
        self._render_builder()
        return Ok(builder)

    def _is_conditional(self, node_id: str) -> bool:
        """True if `node_id` already routes via ON_TRUE/ON_FALSE (an if/else node)."""
        node = next((n for n in self._builder.nodes if n.id == node_id), None)
        if node is None:
            return False
        return any(
            edge.kind in (EdgeKind.ON_TRUE, EdgeKind.ON_FALSE) for edge in node.edges
        )

    def set_cursor(self, node_id: str) -> Result[str, str]:
        """Point the cursor at an existing node (new connections attach from it)."""
        if node_id not in set(self._builder.node_ids):
            return Err(f"no node '{node_id}' to select")
        self._cursor = node_id
        self._render_builder()
        return Ok(node_id)

    def delete_node(self, node_id: str) -> Result[GraphBuilder, str]:
        """Drop a node from the graph — undo an agent card added by accident.

        Every edge pointing at it is removed too (see GraphBuilder.remove_node),
        and the cursor lands on the node's left neighbour so the next card still
        chains from a live node instead of a dangling reference.
        """
        prior_ids = self._builder.node_ids
        removed = self._builder.remove_node(node_id)
        if isinstance(removed, Err):
            return removed
        self._builder = removed.value
        self._builder_status = {}
        self._cursor = self._cursor_after_removal(prior_ids, node_id)
        self._render_builder()
        return removed

    def _cursor_after_removal(
        self, prior_ids: tuple[str, ...], removed_id: str
    ) -> str | None:
        """Pick the cursor after a delete: the removed node's left neighbour."""
        remaining = self._builder.node_ids
        if not remaining:
            return None
        if self._cursor in remaining:  # a *different* node was removed
            return self._cursor
        index = prior_ids.index(removed_id)
        left = [node_id for node_id in prior_ids[:index] if node_id in remaining]
        return left[-1] if left else remaining[0]

    def set_node_repeat(self, node_id: str, times: int) -> Result[GraphBuilder, str]:
        """Set how many times a node runs in place."""
        updated = self._builder.set_repeat(node_id, times)
        if isinstance(updated, Err):
            return updated
        self._builder = updated.value
        self._render_builder()
        return updated

    def make_branch(
        self, from_id: str, true_to: str, false_to: str, condition: str
    ) -> Result[GraphBuilder, str]:
        """Turn a node into an if/else: ON_TRUE→true_to, ON_FALSE→false_to."""
        branched = self._builder.branch(from_id, true_to, false_to, condition)
        if isinstance(branched, Err):
            return branched
        self._builder = branched.value
        self._render_builder()
        return branched

    def add_if_else_cards(
        self,
        from_id: str,
        *,
        condition: str,
        if_ref: str,
        else_ref: str,
        if_text: str = "",
        else_text: str = "",
        if_prompt: str = "",
        else_prompt: str = "",
    ) -> Result[GraphBuilder, str]:
        """Create two branch cards from selected agents and route `from_id` to them."""
        for label, ref in (("IF", if_ref), ("ELSE", else_ref)):
            resolved = self._catalog.resolve(ref)
            if isinstance(resolved, Err):
                return Err(f"{label} agent: {resolved.error}")

        branched = self._builder.branch_to_new_cards(
            from_id,
            condition,
            if_ref,
            else_ref,
            true_text=if_text,
            false_text=else_text,
            true_prompt=if_prompt,
            false_prompt=else_prompt,
        )
        if isinstance(branched, Err):
            return branched
        self._builder = branched.value
        self._builder_status = {}
        self._cursor = self._builder.node_ids[-1]
        self._render_builder()
        return branched


    def _cursor_step(self, delta: int) -> None:
        ids = self._builder.node_ids
        if not ids:
            return
        here = ids.index(self._cursor) if self._cursor in ids else 0
        self._cursor = ids[(here + delta) % len(ids)]
        self._render_builder()

    def action_cursor_prev(self) -> None:
        self._cursor_step(-1)

    def action_cursor_next(self) -> None:
        self._cursor_step(1)

    def action_loop_node(self) -> None:
        if self._cursor is None:
            self.notify("add or select a node first", severity="warning")
            return
        node = next((n for n in self._builder.nodes if n.id == self._cursor), None)
        current = node.repeat if node is not None else 1
        self.push_screen(RepeatEditor(self._cursor, current), self._on_repeat_closed)

    def _on_repeat_closed(self, times: int | None) -> None:
        if times is None or self._cursor is None:
            return
        result = self.set_node_repeat(self._cursor, times)
        if isinstance(result, Err):
            self.notify(result.error, title="Loop failed", severity="error")

    def action_branch_node(self) -> None:
        if self._cursor is None:
            self.notify("add or select a node first", severity="warning")
            return
        agents = self._catalog.of_kind(NodeKind.AGENT)
        if not agents:
            self.notify("discover an agent before creating if/else", severity="warning")
            return
        self.push_screen(BranchEditor(self._cursor, agents), self._on_branch_closed)

    def _on_branch_closed(self, spec: IfElseSpec | None) -> None:
        if spec is None or self._cursor is None:
            return
        result = self.add_if_else_cards(
            self._cursor,
            condition=spec.condition,
            if_ref=spec.if_ref,
            else_ref=spec.else_ref,
            if_text=spec.if_text,
            else_text=spec.else_text,
            if_prompt=spec.if_prompt,
            else_prompt=spec.else_prompt,
        )
        if isinstance(result, Err):
            self.notify(result.error, title="If/else failed", severity="error")

    def action_delete_node(self) -> None:
        if self._cursor is None:
            self.notify("add or select a node first", severity="warning")
            return
        result = self.delete_node(self._cursor)
        if isinstance(result, Err):
            self.notify(result.error, title="Delete failed", severity="error")

    def apply_wire(self, text: str) -> Result[GraphBuilder, str]:
        """Add an edge to the graph-under-construction from a wire command."""
        parsed = parse_wire(text)
        if isinstance(parsed, Err):
            return parsed
        from_id, to_id, kind, condition = parsed.value
        connected = self._builder.connect(from_id, to_id, kind, condition)
        if isinstance(connected, Err):
            return connected
        self._builder = connected.value
        self._render_builder()
        return connected

    def action_clear_builder(self) -> None:
        self._builder = GraphBuilder(name=self._builder.name, description=self._builder.description)
        self._builder_status = {}
        self._cursor = None
        self._render_builder()

    def action_edit_agent(self) -> None:
        """Open the editor for the highlighted agent card."""
        cards = self.query_one(AgentCards)
        if cards.highlighted is None:
            self.notify("highlight an agent card first", severity="warning")
            return
        option = cards.get_option_at_index(cards.highlighted)
        node = next((n for n in self._catalog.nodes if n.key == option.id), None)
        if node is None:
            return
        self.push_screen(CardEditor(node), self._on_editor_closed)

    def _on_editor_closed(self, edited: CatalogNode | None) -> None:
        if edited is None:
            return
        result = self.edit_agent(
            edited, description=edited.description, tools=edited.tools, model=edited.model
        )
        if isinstance(result, Err):
            self.notify(result.error, title="Edit failed", severity="error")
        else:
            self.notify(f"Saved '{edited.name}'")

    def edit_agent(
        self,
        node: CatalogNode,
        *,
        description: str,
        tools: tuple[str, ...],
        model: str | None,
    ) -> Result[Path, str]:
        """Persist edits to an agent's .claude definition, then re-scan the catalog."""
        edited = replace(node, description=description, tools=tools, model=model)
        written = write_node(edited)
        if isinstance(written, Ok):
            self.action_refresh()
        return written

    def action_save_builder(self) -> None:
        self._save_builder_worker()

    @work(exclusive=True)
    async def _save_builder_worker(self) -> None:
        name = await self.push_screen_wait(NameEditor(self._builder.name))
        if name is None:
            return  # cancelled — leave the canvas untouched, write nothing
        self._builder = replace(self._builder, name=name)
        result = await self.save_builder()
        if isinstance(result, Err):
            self.notify(result.error, title="Save failed", severity="error")
            return
        graph = result.value
        self.notify(f"Saved graph '{graph.name}' and exported its slash command")

    def action_run_builder(self) -> None:
        self._run_builder_worker()

    @work(exclusive=True)
    async def _run_builder_worker(self) -> None:
        result = await self.run_builder()
        if isinstance(result, Err):
            self.notify(result.error, title="Graph run failed", severity="error")
            return
        report = result.value
        outcome = "completed" if report.ok else f"stopped: {report.stopped}"
        self.notify(f"Saved & ran graph — {outcome}")

    async def _build_and_save(self) -> Result[Graph, str]:
        """Build+validate the builder graph and persist its YAML — no command, no run.

        The shared first half of both `s` (save + export) and `x` (save + run): a
        graph that will not validate is never written, so a half-wired canvas can't
        masquerade as a saved flow.
        """
        built = self._builder.build()
        if isinstance(built, Err):
            return built
        graph = built.value
        saved = await asyncio.to_thread(save_graph, graph, self._graphs_dir)
        if isinstance(saved, Err):
            return saved
        return Ok(graph)

    async def save_builder(self) -> Result[Graph, str]:
        """`s` — persist the graph YAML and export its self-contained slash command.

        The command write is offloaded to a thread because the CrewAI writer may call
        a model, which must not block the UI.
        """
        saved = await self._build_and_save()
        if isinstance(saved, Err):
            return saved
        graph = saved.value
        command = await asyncio.to_thread(
            write_graph_command,
            graph,
            self._commands_dir(),
            writer=self._graph_command_writer,
        )
        if isinstance(command, Err):
            return command
        return Ok(graph)

    async def run_builder(self) -> Result[GraphReport, str]:
        """`x` — persist the graph YAML, then execute it live (save + execute)."""
        saved = await self._build_and_save()
        if isinstance(saved, Err):
            return saved
        graph = saved.value
        self._builder_status = {}
        self._render_builder()
        report = await run_graph(
            graph,
            self._catalog,
            self._runner,
            self._condition,
            goal=graph.description,
            on_event=self._on_builder_event,
        )
        self._render_builder()
        return report

    def _on_builder_event(self, event: NodeEvent) -> None:
        self._builder_status[event.node_id] = event.status
        self._render_builder()

    def _render_builder(self) -> None:
        self.query_one(GraphBuilderPanel).show(
            self._builder, self._builder_status, self._cursor
        )

    # --- run a flow --------------------------------------------------------

    @work(exclusive=True)
    async def _run_worker(self, name: str) -> None:
        result = await self.run_flow_by_name(name)
        if isinstance(result, Err):
            self.notify(result.error, title="Run failed", severity="error")
            return
        report = result.value
        outcome = "completed" if report.ok else "finished with failures"
        self.notify(f"Flow '{name}' {outcome}")

    async def run_flow_by_name(self, name: str) -> Result[RunReport, str]:
        flow = self._flows.get(name)
        if flow is None:
            return Err(f"no saved flow named '{name}'")
        return await self.run_flow(flow)

    async def run_flow(self, flow: Flow) -> Result[RunReport, str]:
        """Execute `flow`, streaming each node's status into the RunPanel live.

        Running a flow also (re)writes its Claude slash command, so a run always
        leaves a `/<flow>` command on disk — including for flows saved before
        command authoring existed. The command is a convenience, not the run's
        purpose: a write failure is surfaced as a warning and never aborts the
        run. The write is offloaded to a thread because the CrewAI writer may
        call a model, which must not block the UI mid-run.
        """
        self._current_flow = flow
        self._run_status = {}
        self._render_run()
        await self._write_flow_command(flow)
        report = await execute(
            flow,
            self._catalog,
            self._runner,
            goal=flow.description,
            on_event=self._on_node_event,
        )
        self._render_run()
        return report

    async def _write_flow_command(self, flow: Flow) -> None:
        """(Re)write the flow's slash command; warn on failure, never abort a run."""
        written = await asyncio.to_thread(
            write_flow_command,
            flow,
            self._commands_dir(),
            flows_dir=self._flows_dir,
            writer=self._command_writer,
        )
        if isinstance(written, Err):
            self.notify(written.error, title="Command not written", severity="warning")

    def _on_node_event(self, event: NodeEvent) -> None:
        self._run_status[event.node_id] = event.status
        self._render_run()

    def _render_run(self) -> None:
        panel = self.query_one(RunPanel)
        panel.show(self._current_flow, self._run_status)
        if self._current_flow is not None:
            panel.border_title = f"RUN ▸ {self._current_flow.name}"


def run() -> None:
    DeVinciApp().run()
