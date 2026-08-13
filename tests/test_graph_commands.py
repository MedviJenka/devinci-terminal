"""Graph command authoring — a saved graph becomes a self-contained slash command.

Unlike a flow command (a thin `--run-flow` shell shim), a graph command embeds the
whole orchestration: every agent, its instruction, and the branch/loop routing, so
the `/command` runs the flow end to end without the DeVinci runtime. CrewAI drafts
it; a deterministic orchestration is written when the draft is missing or invalid.
"""

from __future__ import annotations

from pathlib import Path

from common.result import Err, Ok, Result
from discovery import NodeKind, scan
from flows.commands import GraphCommandWriter, write_graph_command
from flows.graph import Edge, EdgeKind, Graph, GraphNode


class FakeGraphWriter:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.calls: list[tuple[Graph, str]] = []

    def write(self, graph: Graph, *, command_name: str) -> Result[str, str]:
        self.calls.append((graph, command_name))
        return self._reply


def _graph(name: str = "ship") -> Graph:
    return Graph(
        name=name,
        description="plan then build or fix",
        entry="plan",
        nodes=(
            GraphNode(id="plan", ref="agent:planner", edges=(Edge(to="build"),)),
            GraphNode(
                id="build",
                ref="agent:coder",
                repeat=3,
                prompt="write the code",
                edges=(
                    Edge(to="done", kind=EdgeKind.ON_TRUE, condition="tests pass"),
                    Edge(to="build", kind=EdgeKind.ON_FALSE, condition="tests pass"),
                ),
            ),
            GraphNode(id="done", ref="agent:releaser"),
        ),
    )


def _valid_markdown() -> str:
    return (
        "---\n"
        "description: Run DeVinci flow 'ship'\n"
        "allowed-tools: Task\n"
        "---\n\n"
        "Orchestrate: Task planner, then Task coder, then Task releaser.\n"
    )


def test_write_graph_command_uses_writer_draft_and_is_discoverable(tmp_path: Path) -> None:
    claude_root = tmp_path / ".claude"
    commands_dir = claude_root / "commands"
    writer = FakeGraphWriter(Ok(_valid_markdown()))

    result = write_graph_command(_graph(), commands_dir, writer=writer)

    assert isinstance(result, Ok)
    assert result.value == commands_dir / "ship.md"
    assert result.value.read_text(encoding="utf-8") == _valid_markdown()
    assert writer.calls == [(_graph(), "ship")]
    discovered = scan((claude_root,)).find(NodeKind.COMMAND, "ship")
    assert discovered is not None


def test_write_graph_command_falls_back_to_embedded_orchestration(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    writer = FakeGraphWriter(Ok("not a command"))

    result = write_graph_command(_graph(), commands_dir, writer=writer)

    assert isinstance(result, Ok)
    text = result.value.read_text(encoding="utf-8")
    # Self-contained: it names every agent and the branch/loop routing, and never
    # shells back into the DeVinci runtime.
    assert "agent:planner" in text
    assert "agent:coder" in text
    assert "agent:releaser" in text
    assert "tests pass" in text
    assert "repeat" in text.lower()
    assert "--run-graph" not in text
    assert "--run-flow" not in text


def test_write_graph_command_rejects_unusable_name(tmp_path: Path) -> None:
    result = write_graph_command(_graph("///"), tmp_path / ".claude" / "commands")

    assert isinstance(result, Err)
    assert "command name" in result.error


def test_graph_command_writer_protocol_is_structural() -> None:
    assert isinstance(FakeGraphWriter(Ok(_valid_markdown())), GraphCommandWriter)
