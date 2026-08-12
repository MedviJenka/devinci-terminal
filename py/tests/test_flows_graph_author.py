"""Agentic graph authoring — a goal + catalog become a validated control-flow Graph.

The model designs a graph with typed edges (NEXT / ON_TRUE / ON_FALSE) and loops
via back-edges. The author guarantees runnability: refs resolve in the catalog and
the graph passes structural validation. Completion is injected (fake here).
"""

from __future__ import annotations

import json
from pathlib import Path

from common.result import Err, Ok, Result
from discovery import Catalog, CatalogNode, NodeKind
from flows.graph import EdgeKind
from flows.graph_author import author_graph


def _catalog(*names: str) -> Catalog:
    catalog = Catalog()
    for name in names:
        catalog.add(
            CatalogNode(
                kind=NodeKind.AGENT,
                name=name,
                description=f"{name}",
                source=Path(f"/fake/{name}.md"),
            )
        )
    return catalog


class FakeCompletion:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.prompt: str | None = None

    def complete(self, prompt: str) -> Result[str, str]:
        self.prompt = prompt
        return self._reply


def _loop_reply() -> Result[str, str]:
    return Ok(
        json.dumps(
            {
                "name": "ship",
                "description": "code/review loop then test",
                "entry": "prd",
                "max_visits": 4,
                "nodes": [
                    {"id": "prd", "ref": "agent:prd", "edges": [{"to": "code"}]},
                    {"id": "code", "ref": "agent:code", "edges": [{"to": "review"}]},
                    {
                        "id": "review",
                        "ref": "agent:review",
                        "edges": [
                            {"to": "test", "kind": "on_true", "condition": "review passed"},
                            {"to": "code", "kind": "on_false", "condition": "review passed"},
                        ],
                    },
                    {"id": "test", "ref": "agent:test"},
                ],
            }
        )
    )


def test_valid_reply_becomes_a_graph_with_typed_edges() -> None:
    completion = FakeCompletion(_loop_reply())
    result = author_graph(
        "build with a review loop", _catalog("prd", "code", "review", "test"), completion
    )

    assert isinstance(result, Ok)
    graph = result.value
    assert graph.entry == "prd"
    assert graph.max_visits == 4
    review = graph.by_id("review")
    kinds = {edge.kind for edge in review.edges}
    assert kinds == {EdgeKind.ON_TRUE, EdgeKind.ON_FALSE}


def test_reply_in_markdown_fences_still_parses() -> None:
    inner = json.dumps(
        {
            "name": "x",
            "description": "",
            "entry": "a",
            "nodes": [{"id": "a", "ref": "agent:prd"}],
        }
    )
    completion = FakeCompletion(Ok(f"Sure:\n```json\n{inner}\n```"))
    result = author_graph("do a thing", _catalog("prd"), completion)
    assert isinstance(result, Ok)
    assert result.value.entry == "a"


def test_ref_not_in_catalog_is_err() -> None:
    reply = Ok(
        json.dumps(
            {
                "name": "x",
                "description": "",
                "entry": "a",
                "nodes": [{"id": "a", "ref": "agent:ghost"}],
            }
        )
    )
    result = author_graph("g", _catalog("prd"), FakeCompletion(reply))
    assert isinstance(result, Err)
    assert "agent:ghost" in result.error


def test_structurally_invalid_graph_is_err() -> None:
    # edge to a node that doesn't exist -> validate_graph rejects it
    reply = Ok(
        json.dumps(
            {
                "name": "x",
                "description": "",
                "entry": "a",
                "nodes": [{"id": "a", "ref": "agent:prd", "edges": [{"to": "ghost"}]}],
            }
        )
    )
    result = author_graph("g", _catalog("prd"), FakeCompletion(reply))
    assert isinstance(result, Err)


def test_prompt_teaches_edge_kinds_and_lists_palette() -> None:
    completion = FakeCompletion(_loop_reply())
    author_graph("g", _catalog("prd", "code"), completion)

    prompt = completion.prompt
    assert prompt is not None
    assert "on_true" in prompt and "on_false" in prompt
    assert "agent:prd" in prompt
    assert "loop" in prompt.lower()


def test_completion_error_propagates() -> None:
    result = author_graph("g", _catalog("prd"), FakeCompletion(Err("down")))
    assert isinstance(result, Err)
    assert "down" in result.error


def test_malformed_json_is_err() -> None:
    result = author_graph("g", _catalog("prd"), FakeCompletion(Ok("not json")))
    assert isinstance(result, Err)


def test_empty_goal_is_err_without_calling_model() -> None:
    completion = FakeCompletion(_loop_reply())
    result = author_graph("  ", _catalog("prd"), completion)
    assert isinstance(result, Err)
    assert completion.prompt is None
