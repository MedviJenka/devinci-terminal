"""Agentic control-flow graph authoring — a goal becomes a runnable Graph.

Like author_flow, but the model designs a control-flow graph with typed edges
(sequence, and conditional branches that also form loops via back-edges) instead
of a plain DAG. The result is guaranteed runnable: every ref resolves in the
catalog and the graph passes structural validation, else Err.
"""

from __future__ import annotations

from common.logging import get_logger
from common.result import Err, Result
from discovery import Catalog
from flows.graph import DEFAULT_MAX_VISITS, Graph, validate_graph
from flows.parsing import extract_json_object, parse_graph_mapping
from runtime.completion import Completion

__all__ = ["author_graph", "build_graph_prompt"]

logger = get_logger(__name__)


def author_graph(goal: str, catalog: Catalog, completion: Completion) -> Result[Graph, str]:
    """Design a validated control-flow Graph for `goal` from `catalog`'s nodes."""
    goal = goal.strip()
    if not goal:
        logger.warning("author_graph_rejected", reason="empty goal")
        return Err("goal must not be empty")

    logger.info("author_graph_started", goal=goal, catalog_size=len(catalog.nodes))

    reply = completion.complete(build_graph_prompt(goal, catalog))
    if isinstance(reply, Err):
        logger.error("author_graph_completion_failed", goal=goal, error=reply.error)
        return reply

    payload = extract_json_object(reply.value)
    if isinstance(payload, Err):
        logger.error("author_graph_unparseable_reply", goal=goal, error=payload.error)
        return payload

    graph = parse_graph_mapping(payload.value, context="authored graph")
    if isinstance(graph, Err):
        logger.error("author_graph_invalid_shape", goal=goal, error=graph.error)
        return graph

    unresolved = _unresolved_refs(graph.value, catalog)
    if unresolved:
        logger.error("author_graph_unresolved_refs", goal=goal, refs=unresolved)
        return Err(f"authored graph references unknown node(s): {', '.join(unresolved)}")

    validated = validate_graph(graph.value)
    if isinstance(validated, Err):
        logger.error("author_graph_invalid_structure", goal=goal, error=validated.error)
    else:
        logger.info(
            "author_graph_succeeded", goal=goal, name=validated.value.name,
            nodes=len(validated.value.nodes),
        )
    return validated


def build_graph_prompt(goal: str, catalog: Catalog) -> str:
    """Compose the design prompt: goal, palette, and the control-flow contract."""
    palette = "\n".join(f"- {node.key}: {node.description}" for node in catalog.nodes)
    return (
        "You are designing a reusable orchestration flow as a CONTROL-FLOW GRAPH. "
        "Nodes run one at a time starting from 'entry'; each node's outgoing edges "
        "decide what runs next.\n\n"
        f"GOAL:\n{goal}\n\n"
        f"AVAILABLE NODES (use these exact 'ref' keys):\n{palette}\n\n"
        "EDGE KINDS:\n"
        "- 'next': unconditional — run the target next.\n"
        "- 'on_true' / 'on_false': a conditional pair on the SAME node; after it "
        "runs, its output is judged against 'condition' and the matching branch is "
        "taken. A node with a conditional MUST declare both on_true and on_false.\n"
        "- LOOP: to loop, point an on_false (or on_true) edge BACK to an earlier "
        "node — e.g. review on_false -> code. Loops are capped by 'max_visits'.\n\n"
        "Node fields: 'text' is an optional visible card label; 'prompt' is "
        "optional per-card guidance passed to that agent at runtime.\n\n"
        "Reply with ONE JSON object and nothing else:\n"
        "{\n"
        '  "name": "kebab-case-name",\n'
        '  "description": "one line",\n'
        '  "entry": "id-of-first-node",\n'
        f'  "max_visits": {DEFAULT_MAX_VISITS},\n'
        '  "nodes": [\n'
        '    {"id": "code", "ref": "<a key above>", "prompt": "implementation guidance", "edges": [{"to": "review"}]},\n'
        '    {"id": "review", "ref": "<a key above>", "text": "review gate", "edges": [\n'
        '      {"to": "test", "kind": "on_true", "condition": "the work passes review"},\n'
        '      {"to": "code", "kind": "on_false", "condition": "the work passes review"}\n'
        "    ]}\n"
        "  ]\n"
        "}\n"
        "Rules: every 'ref' is one of the keys above; ids are unique; 'entry' and "
        "every edge 'to' name real node ids; a terminal node has no edges."
    )


def _unresolved_refs(graph: Graph, catalog: Catalog) -> list[str]:
    known = {node.key for node in catalog.nodes}
    seen: list[str] = []
    for node in graph.nodes:
        if node.ref not in known and node.ref not in seen:
            seen.append(node.ref)
    return seen
