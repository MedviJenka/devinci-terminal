"""ClaudeCodeRunner — executes any catalog node via the Completion boundary.

Unlike the old CrewAI premise, a node runs by prompting Claude Code headless with
the node's role and the composed inputs, so every kind (agent/skill/command) is
executable. The Completion is injected, so these tests use a fake.
"""

from __future__ import annotations

from pathlib import Path

from common.result import Err, Ok, Result
from discovery import CatalogNode, NodeKind
from runtime.runner import ClaudeCodeRunner, NodeRunner


class FakeCompletion:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.prompt: str | None = None

    def complete(self, prompt: str) -> Result[str, str]:
        self.prompt = prompt
        return self._reply


def _node(kind: NodeKind = NodeKind.AGENT, name: str = "coder") -> CatalogNode:
    return CatalogNode(
        kind=kind,
        name=name,
        description=f"the {name} node",
        source=Path(f"/fake/{name}.md"),
    )


def test_run_prompts_with_node_role_and_inputs_and_returns_reply() -> None:
    completion = FakeCompletion(Ok("did the work"))
    runner = ClaudeCodeRunner(completion)

    result = runner.run(_node(name="coder"), "build the feature")

    assert isinstance(result, Ok)
    assert result.value == "did the work"
    assert completion.prompt is not None
    assert "coder" in completion.prompt
    assert "build the feature" in completion.prompt


def test_run_executes_non_agent_kinds_too() -> None:
    completion = FakeCompletion(Ok("ran command"))
    result = ClaudeCodeRunner(completion).run(
        _node(kind=NodeKind.COMMAND, name="release"), "ship it"
    )
    assert isinstance(result, Ok)


def test_completion_error_propagates() -> None:
    result = ClaudeCodeRunner(FakeCompletion(Err("claude failed"))).run(_node(), "x")
    assert isinstance(result, Err)
    assert "claude failed" in result.error


def test_satisfies_node_runner_protocol() -> None:
    assert isinstance(ClaudeCodeRunner(FakeCompletion(Ok("x"))), NodeRunner)
