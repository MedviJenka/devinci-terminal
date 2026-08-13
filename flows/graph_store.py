"""
Persist control-flow Graphs as YAML — the builder's "save this graph" boundary.

Graphs live in their own directory, apart from Flow YAML: a Graph's richer shape
(typed edges, loops, per-node repeat) is not a Flow, and sharing a directory would
let list_flows silently misread a graph as a lossy flow. Loading is a trust
boundary between raw files and the typed model — it parses defensively, then runs
the same structural validation the interpreter demands, and returns a Result
rather than raising. The on-disk shape mirrors the model:

    name: ship
    description: plan then build then verify
    entry: plan
    max_visits: 5
    nodes:
      - id: plan
        ref: agent:planner
        edges:
          - to: build
      - id: build
        ref: agent:coder
        repeat: 2
        edges:
          - to: verify
            kind: on_true
            condition: compiles
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from common.result import Err, Ok, Result
from flows.graph import Edge, EdgeKind, Graph, GraphNode, validate_graph
from flows.parsing import parse_graph_mapping

__all__ = ["save_graph", "load_graph", "list_graphs"]

MAX_GRAPHS = 1000  # bound on files a single directory listing will parse


def save_graph(graph: Graph, directory: Path) -> Result[Path, str]:
    """Write `graph` to `<directory>/<name>.yaml`; return the path or an error."""
    payload = {
        "name": graph.name,
        "description": graph.description,
        "entry": graph.entry,
        "max_visits": graph.max_visits,
        "nodes": [_graph_node_to_dict(node) for node in graph.nodes],
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{graph.name}.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return Ok(path)
    except OSError as exc:
        return Err(f"could not write graph '{graph.name}': {exc}")


def load_graph(path: Path) -> Result[Graph, str]:
    """Read, parse, and structurally validate a graph file, or explain why not."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return Err(f"could not read graph file '{path}': {exc}")

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return Err(f"invalid YAML in '{path}': {exc}")

    parsed = parse_graph_mapping(raw, context=f"graph '{path}'")
    if isinstance(parsed, Err):
        return parsed
    return validate_graph(parsed.value)


def list_graphs(directory: Path) -> tuple[Graph, ...]:
    """Load every well-formed *.yaml graph in `directory`; skip the malformed."""
    if not directory.is_dir():
        return ()
    graphs = []
    for path in sorted(directory.glob("*.yaml"))[:MAX_GRAPHS]:
        result = load_graph(path)
        if isinstance(result, Ok):
            graphs.append(result.value)
    return tuple(graphs)


def _graph_node_to_dict(node: GraphNode) -> dict[str, Any]:
    # Omit fields left at their default so saved files stay minimal and readable.
    out: dict[str, Any] = {"id": node.id, "ref": node.ref}
    if node.edges:
        out["edges"] = [_edge_to_dict(edge) for edge in node.edges]
    if node.repeat != 1:
        out["repeat"] = node.repeat
    if node.text:
        out["text"] = node.text
    if node.prompt:
        out["prompt"] = node.prompt
    return out


def _edge_to_dict(edge: Edge) -> dict[str, Any]:
    out: dict[str, Any] = {"to": edge.to}
    if edge.kind is not EdgeKind.NEXT:
        out["kind"] = edge.kind.value
    if edge.condition:
        out["condition"] = edge.condition
    return out
