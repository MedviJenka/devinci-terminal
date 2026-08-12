"""Agentic flow authoring — turn a natural-language goal into a runnable Flow.

`author_flow` presents the discovered catalog as a palette to a model (via the
injected Completion interface — the LLM boundary, backed by Claude Code headless
in production), asks it to design a DAG, then *guarantees* the result is runnable:
the reply is parsed defensively, every node ref must resolve in the catalog, and
the graph must be acyclic. Anything short of that returns Err rather than handing
back a flow that would fail at execution time.
"""

from __future__ import annotations

from common.result import Err, Result
from discovery import Catalog
from flows.models import Flow
from flows.parsing import extract_json_object, parse_flow_mapping
from flows.topo import topo_layers
from runtime.completion import Completion

__all__ = ["Completion", "author_flow", "build_prompt"]


def author_flow(goal: str, catalog: Catalog, completion: Completion) -> Result[Flow, str]:
    """Design a validated Flow for `goal` from `catalog`'s nodes, or explain why not."""
    goal = goal.strip()
    if not goal:
        return Err("goal must not be empty")

    reply = completion.complete(build_prompt(goal, catalog))
    if isinstance(reply, Err):
        return reply

    payload = extract_json_object(reply.value)
    if isinstance(payload, Err):
        return payload

    flow = parse_flow_mapping(payload.value, context="authored flow")
    if isinstance(flow, Err):
        return flow

    unresolved = _unresolved_refs(flow.value, catalog)
    if unresolved:
        return Err(f"authored flow references unknown node(s): {', '.join(unresolved)}")

    layers = topo_layers(flow.value)
    if isinstance(layers, Err):
        return layers

    return flow


def build_prompt(goal: str, catalog: Catalog) -> str:
    """Compose the design prompt: the goal, the available palette, output contract."""
    palette = "\n".join(f"- {node.key}: {node.description}" for node in catalog.nodes)
    return (
        "You are designing a reusable orchestration flow as a directed acyclic "
        "graph (DAG). Choose from ONLY the available nodes below and wire them "
        "with dependencies.\n\n"
        f"GOAL:\n{goal}\n\n"
        f"AVAILABLE NODES (use these exact 'ref' keys):\n{palette}\n\n"
        "Reply with ONE JSON object and nothing else:\n"
        "{\n"
        '  "name": "kebab-case-flow-name",\n'
        '  "description": "one line",\n'
        '  "nodes": [\n'
        '    {"id": "step-id", "ref": "<one of the keys above>", '
        '"after": ["ids that must finish first"]}\n'
        "  ]\n"
        "}\n"
        "Rules: every 'ref' must be one of the keys above; 'id' is unique within "
        "the flow; 'after' lists other node ids (omit or [] for entry points); "
        "the graph must be acyclic."
    )


def _unresolved_refs(flow: Flow, catalog: Catalog) -> list[str]:
    known = {node.key for node in catalog.nodes}
    seen: list[str] = []
    for node in flow.nodes:
        if node.ref not in known and node.ref not in seen:
            seen.append(node.ref)
    return seen
