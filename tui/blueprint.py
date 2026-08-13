"""
Blueprint canvas — draws a control-flow Graph as a horizontal card strip.

Pure rendering: given a `Graph` (and optionally a live `{node_id: NodeStatus}`
map), build a Rich renderable laid out left-to-right — each node is a rounded
card (its id + dim ref), consecutive cards are joined by a labeled connector, a
repeating/back-edge node carries a `↻ loop` connector, and a conditional node
fans into two branches whose *target nodes are drawn as cards*: the `(if)` target
up-right, the `(else)` target down-right off a center junction. Each branch then
keeps drawing its own NEXT-chain in its band — cards added onto an if/else card
(by moving the cursor onto it) render alongside it, not just in the node count.
Never raises.

The canvas is a fixed grid of rows built block-by-block (card, connector, fork);
fork-free graphs occupy the center band and are trimmed back to three rows. The
main strip walks `graph.nodes` order until a node forks or has no successor, and
each branch band does the same starting from its target — one fork deep only; a
branch card that itself forks again is flagged `⋯` rather than drawn, so this is
a linear-with-one-branch-of-linear-branches shape, not an arbitrary DAG.
"""

from __future__ import annotations

from typing import Optional
from rich.text import Text
from rich.console import Group
from collections.abc import Iterable
from flows.executor import NodeStatus
from tui.theme import OH_MY_PI, hex_of
from flows.graph import Edge, EdgeKind, Graph, GraphNode


__all__ = ["render_blueprint"]

# Status glyph + palette colour per node state (kept in step with app.py's run view).
_STATUS_STYLE: dict[NodeStatus, tuple[str, tuple[int, int, int]]] = {
    NodeStatus.RUNNING: ("◐", OH_MY_PI["amber"]),
    NodeStatus.SUCCEEDED: ("●", OH_MY_PI["lime"]),
    NodeStatus.FAILED: ("✗", OH_MY_PI["red"]),
    NodeStatus.SKIPPED: ("◌", OH_MY_PI["slate"]),
}

_PENDING_STYLE: tuple[str, tuple[int, int, int]] = ("◌", OH_MY_PI["slate"])

# Palette styles reused across the canvas.
_WIRE = hex_of(OH_MY_PI["violet"])

_LOOP = hex_of(OH_MY_PI["pink"]) + " bold"

_IF = hex_of(OH_MY_PI["lime"]) + " bold"

_ELSE = hex_of(OH_MY_PI["amber"]) + " bold"

# The canvas is 7 rows tall; the linear strip sits on the center band (rows 2-4),
# leaving room for an (if) card above (rows 0-2) and an (else) card below (4-6).
_ROWS = 7
_CENTER_TOP = 2
_JUNCTION = 3  # dashes before the fork's ┤, also the branch-label indent

# A branch band is one atomic unit the wrap pass can't break internally (unlike
# the main strip, made of many small units) — cap how many cards it chains
# before flagging the rest with `⋯` instead of running off the terminal edge.
_MAX_BAND_CHAIN = 3

# A styled span and a full row of spans, the unit blocks are emitted in.
Span = tuple[str, str | None]
Block = list[list[Span]]


def render_blueprint(graph: Graph, statuses: dict[str, Optional[NodeStatus]] = None) -> object:
    """Render `graph` as node cards that wrap cleanly to the available width.

    `statuses` lights each card with its live status glyph/colour; omitted nodes
    show pending. The Rich renderable reads the terminal/panel width at print
    time, so large graphs wrap between card groups instead of corrupting rows.
    """
    if not graph.nodes:
        return Group(Text("  (empty canvas)", style="dim italic"))
    return _BlueprintCanvas(graph, statuses or {})


class _BlueprintCanvas:

    """Rich renderable that packs blueprint blocks to the current console width."""

    def __init__(self, graph: Graph, live: dict[str, NodeStatus]) -> None:
        self._graph = graph
        self._live = live

    def __rich_console__(self, console: object, options: object) -> object:
        max_width = max(
            1, min(getattr(options, "max_width", 80), getattr(console, "width", 80))
        )
        wrapped = _wrap_units(_blueprint_units(self._graph, self._live), max_width)
        for index, units in enumerate(wrapped):
            if index:
                yield Text()
            yield from _trim(_merge_blocks(block for unit in units for block in unit))


def _blueprint_units(graph: Graph, live: dict[str, NodeStatus]) -> list[list[Block]]:
    """Return card/connector units; connectors stay paired with their target card."""
    order = {node.id: index for index, node in enumerate(graph.nodes)}
    units: list[list[Block]] = []
    pending: Block | None = None

    for index, node in enumerate(graph.nodes):
        card = _card_block(node, node.id == graph.entry, live.get(node.id))
        if pending is None:
            units.append([card])
        else:
            units.append([pending, card])
            pending = None

        branch = _branch_edges(node)

        if branch is not None:
            on_true, on_false = branch
            true_loops = order.get(on_true.to, index) < index
            false_loops = order.get(on_false.to, index) < index
            units.append(
                [
                    _spine_block(),
                    _branch_cards_block(
                        graph, live, order, on_true.to, on_false.to, true_loops, false_loops
                    ),
                ]
            )
            break

        nxt = _next_edge(node)

        if nxt is None: break
        looping = node.repeat > 1 or order.get(nxt.to, index) <= index
        pending = _connector_block(looping)

    if pending is not None:
        units.append([pending])

    return units


def _wrap_units(units: list[list[Block]], max_width: int) -> list[list[list[Block]]]:
    """Pack units into visual lines without exceeding `max_width` when possible."""
    lines: list[list[list[Block]]] = []
    current: list[list[Block]] = []
    current_width = 0

    for unit in units:
        width = sum(_block_width(block) for block in unit)
        if current and current_width + width > max_width:
            lines.append(current)
            current = []
            current_width = 0
        current.append(unit)
        current_width += width

    if current:
        lines.append(current)
    return lines


def _merge_blocks(blocks: Iterable[Block]) -> list[Text]:
    rows = [Text(no_wrap=True) for _ in range(_ROWS)]
    for block in blocks:
        _emit(rows, block)
    return rows


def _block_width(block: Block) -> int:
    return max((sum(len(text) for text, _ in row) for row in block), default=0)


def _emit(rows: list[Text], block: Block) -> None:
    """Append one fixed-width block (its rows padded equal) to the canvas rows."""
    width = max(sum(len(text) for text, _ in row) for row in block)
    for canvas_row, spans in zip(rows, block):
        used = 0
        for text, style in spans:
            canvas_row.append(text, style=style)
            used += len(text)
        if used < width:
            canvas_row.append(" " * (width - used))


def _card_block(node: GraphNode, is_entry: bool, status: NodeStatus | None) -> Block:
    """A node card placed on the center band (rows 2-4), blank elsewhere."""
    top, content, bot = _card_rows(node, is_entry, status)
    block: Block = [[] for _ in range(_ROWS)]
    block[_CENTER_TOP] = [top]
    block[_CENTER_TOP + 1] = content
    block[_CENTER_TOP + 2] = [bot]
    return block


def _preview(text: str, limit: int = 28) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"



def _card_rows(
    node: GraphNode, is_entry: bool, status: NodeStatus | None, *, loop: bool = False
) -> tuple[Span, list[Span], Span]:
    """The (top-border, content-spans, bottom-border) of one rounded card."""
    glyph, color = _STATUS_STYLE.get(status, _PENDING_STYLE)
    marker = "▸ " if is_entry else ""
    repeat = f" ×{node.repeat}" if node.repeat > 1 else ""
    loop_mark = " ↻" if loop else ""
    title = f"{glyph} {marker}{node.id}{repeat}{loop_mark}"
    text = _preview(node.text)
    accent = color if status else (OH_MY_PI["cyan"] if is_entry else OH_MY_PI["slate"])
    border = hex_of(accent) + (" bold" if status or is_entry else "")
    inner: list[Span] = [(title, hex_of(color) + " bold")]
    if text:
        inner.extend([("   ", None), (text, hex_of(OH_MY_PI["amber"]))])
    inner.extend([("   ", None), (node.ref, "dim")])
    width = sum(len(part) for part, _ in inner) + 4

    top: Span = ("╭" + "─" * width + "╮", border)
    bot: Span = ("╰" + "─" * width + "╯", border)
    content: list[Span] = [("│", border), ("  ", None), *inner, ("  ", None), ("│", border)]
    return top, content, bot


def _connector_block(looping: bool) -> Block:
    """A left-to-right connector on the center row, blank elsewhere."""
    block: Block = [[] for _ in range(_ROWS)]
    if looping:
        block[_CENTER_TOP + 1] = [(" ──", _WIRE), (" ↻ loop ", _LOOP), ("──▸ ", _WIRE)]
    else:
        block[_CENTER_TOP + 1] = [(" ─────▸ ", _WIRE)]
    return block


def _spine_block() -> Block:
    """The junction that connects the center card up to (if) and down to (else)."""
    indent = " " * _JUNCTION
    block: Block = [[] for _ in range(_ROWS)]
    block[1] = [(indent, None), ("╭─", _WIRE), ("(if) ".ljust(7), _IF), ("▸ ", _WIRE)]
    block[2] = [(indent, None), ("│", _WIRE)]
    block[3] = [("─" * _JUNCTION + "┤", _WIRE)]
    block[4] = [(indent, None), ("│", _WIRE)]
    block[5] = [(indent, None), ("╰─", _WIRE), ("(else) ", _ELSE), ("▸ ", _WIRE)]
    return block


def _branch_cards_block(
    graph: Graph,
    live: dict[str, NodeStatus],
    order: dict[str, int],
    if_ref: str,
    else_ref: str,
    if_loops: bool,
    else_loops: bool,
) -> Block:
    """Both branch targets as card chains — (if) on the upper band, (else) on the
    lower. Each target keeps its own NEXT-chain drawn alongside it (cards added
    off a branch via the cursor), so growing a branch doesn't just raise the node
    count invisibly — it shows up.

    Emitted as one block so both chains share a left edge (padded to equal width).
    """
    block: Block = [[] for _ in range(_ROWS)]
    _place_chain(block, graph, live, order, if_ref, band=0, loops=if_loops)
    _place_chain(block, graph, live, order, else_ref, band=4, loops=else_loops)
    return block


def _place_chain(
    block: Block,
    graph: Graph,
    live: dict[str, NodeStatus],
    order: dict[str, int],
    start_ref: str,
    *,
    band: int,
    loops: bool,
) -> None:
    """Write a branch target's card into `block` at a 3-row band (0-2 up, 4-6 down),
    then keep walking its NEXT-chain in the same band — cards chained onto a
    branch (by moving the cursor onto its card and adding more) render right
    alongside it instead of vanishing.

    Stops at a dead end, a node that itself forks (the canvas is one fork deep —
    a nested branch is flagged with `⋯` rather than drawn), or a back-edge to an
    earlier node (shown as a `↻ loop` connector, matching the main strip).
    A branch target that is itself a loop-back (`loops`) is drawn once, unchained
    — walking forward from it would only replay the graph already drawn above it.
    """
    top_row: list[Span] = []
    mid_row: list[Span] = []
    bot_row: list[Span] = []

    node = graph.by_id(start_ref) or GraphNode(id=start_ref, ref="")
    top, content, bot = _card_rows(node, node.id == graph.entry, live.get(start_ref), loop=loops)
    top_row.append(top)
    mid_row.extend(content)
    bot_row.append(bot)

    index = order.get(start_ref)
    placed = 1
    while not loops and index is not None:
        if _branch_edges(node) is not None:
            mid_row.append((" ⋯", "dim"))
            break
        nxt = _next_edge(node)
        if nxt is None:
            break
        if placed >= _MAX_BAND_CHAIN:
            # A band is one atomic, unwrappable unit (unlike the main strip, which
            # wraps between units) — cap it and say so, rather than silently
            # truncating an over-wide line off the edge of the terminal.
            mid_row.append((" ⋯", "dim"))
            break
        target_index = order.get(nxt.to, index)
        if target_index <= index:
            mid_row.extend([(" ──", _WIRE), (" ↻ loop ", _LOOP), ("──▸ ", _WIRE)])
            break
        mid_row.append((" ─────▸ ", _WIRE))
        index = target_index
        node = graph.nodes[index]
        top, content, bot = _card_rows(node, node.id == graph.entry, live.get(node.id))
        top_row.append(top)
        mid_row.extend(content)
        placed += 1
        bot_row.append(bot)

    block[band] = top_row
    block[band + 1] = mid_row
    block[band + 2] = bot_row


def _trim(rows: list[Text]) -> list[Text]:
    """Drop leading/trailing all-blank rows so fork-free graphs render compactly."""
    filled = [i for i, row in enumerate(rows) if row.plain.strip()]
    return rows[filled[0] : filled[-1] + 1] if filled else rows


def _branch_edges(node: GraphNode) -> tuple[Edge, Edge] | None:
    """The (on_true, on_false) pair if `node` is a conditional, else None."""
    on_true = _edge_of(node, EdgeKind.ON_TRUE)
    on_false = _edge_of(node, EdgeKind.ON_FALSE)
    return (on_true, on_false) if on_true is not None and on_false is not None else None


def _next_edge(node: GraphNode) -> Edge | None:
    return _edge_of(node, EdgeKind.NEXT)


def _edge_of(node: GraphNode, kind: EdgeKind) -> Edge | None:
    return next((edge for edge in node.edges if edge.kind is kind), None)
