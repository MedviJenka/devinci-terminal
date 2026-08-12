"""Blueprint canvas — draws a control-flow Graph as a horizontal card strip.

Pure rendering: given a `Graph` (and optionally a live `{node_id: NodeStatus}`
map), build a Rich renderable laid out left-to-right — each node is a rounded
card (its id + dim ref), consecutive cards are joined by a labeled connector, a
repeating/back-edge node carries a `↻ loop` connector, and a conditional node
fans into two branches whose *target nodes are drawn as cards*: the `(if)` target
up-right, the `(else)` target down-right off a center junction. Never raises.

The canvas is a fixed grid of rows built block-by-block (card, connector, fork);
fork-free graphs occupy the center band and are trimmed back to three rows. The
strip walks `graph.nodes` order until a node forks or has no successor — it
mirrors the builder's linear-with-a-terminal-branch shape, not an arbitrary DAG.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from flows.executor import NodeStatus
from flows.graph import Edge, EdgeKind, Graph, GraphNode
from tui.theme import OH_MY_PI, hex_of

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

# A styled span and a full row of spans, the unit blocks are emitted in.
Span = tuple[str, str | None]
Block = list[list[Span]]


def render_blueprint(
    graph: Graph, statuses: dict[str, NodeStatus] | None = None,
) -> Group:
    """Render `graph` as a horizontal strip of node cards with labeled branches.

    `statuses` lights each card with its live status glyph/colour; omitted nodes
    show pending. Returns a placeholder for a graph with no nodes.
    """
    if not graph.nodes:
        return Group(Text("  (empty canvas)", style="dim italic"))

    live = statuses or {}
    order = {node.id: index for index, node in enumerate(graph.nodes)}
    rows = [Text() for _ in range(_ROWS)]

    for index, node in enumerate(graph.nodes):
        _emit(rows, _card_block(node, node.id == graph.entry, live.get(node.id)))

        branch = _branch_edges(node)
        if branch is not None:
            on_true, on_false = branch
            loops_back = order.get(on_false.to, index) < index
            _emit(rows, _spine_block())
            _emit(rows, _branch_cards_block(graph, live, on_true.to, on_false.to, loops_back))
            break

        nxt = _next_edge(node)
        if nxt is None:
            break
        looping = node.repeat > 1 or order.get(nxt.to, index) <= index
        _emit(rows, _connector_block(looping))

    return Group(*_trim(rows))


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


def _card_rows(
    node: GraphNode, is_entry: bool, status: NodeStatus | None, *, loop: bool = False
) -> tuple[Span, list[Span], Span]:
    """The (top-border, content-spans, bottom-border) of one rounded card."""
    glyph, color = _STATUS_STYLE.get(status, _PENDING_STYLE)
    marker = "▸ " if is_entry else ""
    repeat = f" ×{node.repeat}" if node.repeat > 1 else ""
    loop_mark = " ↻" if loop else ""
    title = f"{glyph} {marker}{node.id}{repeat}{loop_mark}"
    accent = color if status else (OH_MY_PI["cyan"] if is_entry else OH_MY_PI["slate"])
    border = hex_of(accent) + (" bold" if status or is_entry else "")
    width = len(title) + len(node.ref) + 7  # "  {title}   {ref}  "

    top: Span = ("╭" + "─" * width + "╮", border)
    bot: Span = ("╰" + "─" * width + "╯", border)
    content: list[Span] = [
        ("│", border),
        ("  ", None),
        (title, hex_of(color) + " bold"),
        ("   ", None),
        (node.ref, "dim"),
        ("  ", None),
        ("│", border),
    ]
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
    if_ref: str,
    else_ref: str,
    loops_back: bool,
) -> Block:
    """Both branch targets as cards — (if) on the upper band, (else) on the lower.

    Emitted as one block so both cards share a left edge (padded to equal width).
    """
    block: Block = [[] for _ in range(_ROWS)]
    _place_card(block, graph, live, if_ref, band=0)
    _place_card(block, graph, live, else_ref, band=4, loop=loops_back)
    return block


def _place_card(
    block: Block,
    graph: Graph,
    live: dict[str, NodeStatus],
    ref: str,
    *,
    band: int,
    loop: bool = False,
) -> None:
    """Write a branch target's card into `block` at a 3-row band (0-2 up, 4-6 down)."""
    node = graph.by_id(ref) or GraphNode(id=ref, ref="")
    top, content, bot = _card_rows(node, node.id == graph.entry, live.get(ref), loop=loop)
    block[band] = [top]
    block[band + 1] = content
    block[band + 2] = [bot]


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
