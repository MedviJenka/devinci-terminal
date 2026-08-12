"""Agentic flow authoring — a goal + catalog become a validated Flow.

The author depends on a Completion interface (the LLM boundary), so these tests
inject a fake that returns canned replies and captures the prompt. The author's
job is to turn a model's JSON reply into a Flow that is guaranteed runnable:
every ref resolves in the catalog and the graph is acyclic.
"""

from __future__ import annotations

import json
from pathlib import Path

from common.result import Err, Ok, Result
from discovery import Catalog, CatalogNode, NodeKind
from flows.author import Completion, author_flow


def _catalog(*names: str) -> Catalog:
    catalog = Catalog()
    for name in names:
        catalog.add(
            CatalogNode(
                kind=NodeKind.AGENT,
                name=name,
                description=f"{name} agent",
                source=Path(f"/fake/{name}.md"),
            )
        )
    return catalog


class FakeCompletion:
    """Returns a scripted reply and records the prompt it was given."""

    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.prompt: str | None = None

    def complete(self, prompt: str) -> Result[str, str]:
        self.prompt = prompt
        return self._reply


def _reply(nodes: list[dict], name: str = "authored") -> Result[str, str]:
    return Ok(json.dumps({"name": name, "description": "d", "nodes": nodes}))


def test_valid_reply_becomes_a_flow() -> None:
    completion = FakeCompletion(
        _reply(
            [
                {"id": "plan", "ref": "agent:planner"},
                {"id": "build", "ref": "agent:coder", "after": ["plan"]},
            ]
        )
    )
    result = author_flow("ship a feature", _catalog("planner", "coder"), completion)

    assert isinstance(result, Ok)
    flow = result.value
    assert flow.ids == ("plan", "build")
    assert flow.by_id("build").after == ("plan",)


def test_reply_wrapped_in_markdown_fences_still_parses() -> None:
    inner = json.dumps(
        {"name": "x", "description": "", "nodes": [{"id": "a", "ref": "agent:planner"}]}
    )
    completion = FakeCompletion(Ok(f"Here is your flow:\n```json\n{inner}\n```\n"))
    result = author_flow("do a thing", _catalog("planner"), completion)

    assert isinstance(result, Ok)
    assert result.value.ids == ("a",)


def test_malformed_json_is_err() -> None:
    completion = FakeCompletion(Ok("this is not json at all"))
    result = author_flow("goal", _catalog("planner"), completion)
    assert isinstance(result, Err)


def test_ref_not_in_catalog_is_err_naming_the_ref() -> None:
    completion = FakeCompletion(_reply([{"id": "a", "ref": "agent:ghost"}]))
    result = author_flow("goal", _catalog("planner"), completion)

    assert isinstance(result, Err)
    assert "agent:ghost" in result.error


def test_authored_cycle_is_err() -> None:
    completion = FakeCompletion(
        _reply(
            [
                {"id": "a", "ref": "agent:planner", "after": ["b"]},
                {"id": "b", "ref": "agent:coder", "after": ["a"]},
            ]
        )
    )
    result = author_flow("goal", _catalog("planner", "coder"), completion)

    assert isinstance(result, Err)
    assert "cycle" in result.error.lower()


def test_prompt_includes_goal_and_available_node_keys() -> None:
    completion = FakeCompletion(_reply([{"id": "a", "ref": "agent:planner"}]))
    author_flow("REVIEW A PR", _catalog("planner", "reviewer"), completion)

    assert completion.prompt is not None
    assert "REVIEW A PR" in completion.prompt
    assert "agent:planner" in completion.prompt
    assert "agent:reviewer" in completion.prompt


def test_completion_error_propagates() -> None:
    completion = FakeCompletion(Err("model unavailable"))
    result = author_flow("goal", _catalog("planner"), completion)

    assert isinstance(result, Err)
    assert "model unavailable" in result.error


def test_empty_goal_is_err_without_calling_the_model() -> None:
    completion = FakeCompletion(_reply([{"id": "a", "ref": "agent:planner"}]))
    result = author_flow("   ", _catalog("planner"), completion)

    assert isinstance(result, Err)
    assert completion.prompt is None  # short-circuited before the model call


def test_completion_protocol_is_structural() -> None:
    # FakeCompletion satisfies Completion without inheriting it.
    assert isinstance(FakeCompletion(Ok("{}")), Completion)
