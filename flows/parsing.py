"""Validate an untyped mapping into a Flow — the shared dict→Flow boundary.

Both the YAML store (store.py) and the agentic author (author.py) receive a
loosely-typed mapping from outside the trust boundary — a parsed file, or a
model's JSON reply. This module is the single place that checks its shape and
returns a Result, so the two callers can never drift in what they accept.
"""

from __future__ import annotations

import json
from typing import Any

from common.result import Err, Ok, Result
from flows.graph import DEFAULT_MAX_VISITS, Edge, EdgeKind, Graph, GraphNode
from flows.models import Flow, FlowNode

__all__ = ["parse_flow_mapping", "parse_graph_mapping", "extract_json_object"]

# Bound on model-reply size we will attempt to parse — a flow/graph spec is
# small; anything larger is a runaway response, not a spec.
_MAX_JSON_CHARS = 20_000


def parse_flow_mapping(raw: Any, *, context: str = "flow") -> Result[Flow, str]:
    """Turn an untyped mapping into a validated Flow, or explain why it can't.

    `context` prefixes error messages so callers can say where the mapping came
    from (a file path, "authored flow", …).
    """
    if not isinstance(raw, dict):
        return Err(f"{context} must be a mapping at the top level")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        return Err(f"{context} is missing a non-empty 'name'")

    description = raw.get("description", "")
    if not isinstance(description, str):
        return Err(f"{context} has a non-string 'description'")

    raw_nodes = raw.get("nodes", [])
    if not isinstance(raw_nodes, list):
        return Err(f"{context} has a 'nodes' field that is not a list")

    nodes: list[FlowNode] = []
    for index, entry in enumerate(raw_nodes):
        parsed = _parse_node(entry, context, index)
        if isinstance(parsed, Err):
            return parsed
        nodes.append(parsed.value)

    return Ok(Flow(name=name, description=description, nodes=tuple(nodes)))


def _parse_node(entry: Any, context: str, index: int) -> Result[FlowNode, str]:
    if not isinstance(entry, dict):
        return Err(f"{context} node #{index} must be a mapping")

    node_id = entry.get("id")
    if not isinstance(node_id, str) or not node_id:
        return Err(f"{context} node #{index} is missing a non-empty 'id'")

    ref = entry.get("ref")
    if not isinstance(ref, str) or not ref:
        return Err(f"{context} node '{node_id}' is missing a non-empty 'ref'")

    raw_after = entry.get("after", [])
    if not isinstance(raw_after, list) or not all(
        isinstance(a, str) for a in raw_after
    ):
        return Err(f"{context} node '{node_id}' has a malformed 'after' list")

    return Ok(FlowNode(id=node_id, ref=ref, after=tuple(raw_after)))


def extract_json_object(text: str) -> Result[dict[str, Any], str]:
    """Pull the first JSON object out of a model reply (tolerating prose/fences)."""
    if len(text) > _MAX_JSON_CHARS:
        return Err("model reply too large to parse")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return Err("model reply contained no JSON object")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return Err(f"model reply was not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        return Err("model reply JSON was not an object")
    return Ok(parsed)


def parse_graph_mapping(raw: Any, *, context: str = "graph") -> Result[Graph, str]:
    """Turn an untyped mapping into a Graph (structure only; validate separately)."""
    if not isinstance(raw, dict):
        return Err(f"{context} must be a mapping at the top level")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        return Err(f"{context} is missing a non-empty 'name'")

    description = raw.get("description", "")
    if not isinstance(description, str):
        return Err(f"{context} has a non-string 'description'")

    entry = raw.get("entry")
    if not isinstance(entry, str) or not entry:
        return Err(f"{context} is missing a non-empty 'entry'")

    max_visits = raw.get("max_visits", DEFAULT_MAX_VISITS)
    if not isinstance(max_visits, int) or isinstance(max_visits, bool) or max_visits < 1:
        return Err(f"{context} has an invalid 'max_visits' (need an int >= 1)")

    raw_nodes = raw.get("nodes", [])
    if not isinstance(raw_nodes, list):
        return Err(f"{context} has a 'nodes' field that is not a list")

    nodes: list[GraphNode] = []
    for index, entry_node in enumerate(raw_nodes):
        parsed = _parse_graph_node(entry_node, context, index)
        if isinstance(parsed, Err):
            return parsed
        nodes.append(parsed.value)

    return Ok(
        Graph(
            name=name,
            description=description,
            entry=entry,
            nodes=tuple(nodes),
            max_visits=max_visits,
        )
    )


def _parse_graph_node(entry: Any, context: str, index: int) -> Result[GraphNode, str]:
    if not isinstance(entry, dict):
        return Err(f"{context} node #{index} must be a mapping")

    node_id = entry.get("id")
    if not isinstance(node_id, str) or not node_id:
        return Err(f"{context} node #{index} is missing a non-empty 'id'")

    ref = entry.get("ref")
    if not isinstance(ref, str) or not ref:
        return Err(f"{context} node '{node_id}' is missing a non-empty 'ref'")

    raw_edges = entry.get("edges", [])
    if not isinstance(raw_edges, list):
        return Err(f"{context} node '{node_id}' has an 'edges' field that is not a list")

    edges: list[Edge] = []
    for edge_index, raw_edge in enumerate(raw_edges):
        parsed = _parse_edge(raw_edge, context, node_id, edge_index)
        if isinstance(parsed, Err):
            return parsed
        edges.append(parsed.value)

    repeat = entry.get("repeat", 1)
    if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat < 1:
        return Err(f"{context} node '{node_id}' has a 'repeat' that is not an int ≥ 1")

    text = entry.get("text", "")
    if not isinstance(text, str):
        return Err(f"{context} node '{node_id}' has a non-string 'text'")

    prompt = entry.get("prompt", "")
    if not isinstance(prompt, str):
        return Err(f"{context} node '{node_id}' has a non-string 'prompt'")


    return Ok(
        GraphNode(
            id=node_id,
            ref=ref,
            edges=tuple(edges),
            repeat=repeat,
            text=text,
            prompt=prompt,
        )
    )


def _parse_edge(
    raw: Any, context: str, node_id: str, index: int
) -> Result[Edge, str]:
    if not isinstance(raw, dict):
        return Err(f"{context} node '{node_id}' edge #{index} must be a mapping")

    to = raw.get("to")
    if not isinstance(to, str) or not to:
        return Err(f"{context} node '{node_id}' edge #{index} is missing a 'to'")

    kind_str = raw.get("kind", EdgeKind.NEXT.value)
    try:
        kind = EdgeKind(kind_str)
    except ValueError:
        return Err(
            f"{context} node '{node_id}' edge #{index} has unknown kind '{kind_str}'"
        )

    condition = raw.get("condition", "")
    if not isinstance(condition, str):
        return Err(f"{context} node '{node_id}' edge #{index} has a non-string condition")

    return Ok(Edge(to=to, kind=kind, condition=condition))
