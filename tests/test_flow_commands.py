"""Flow command authoring — saved flows become Claude slash commands."""

from __future__ import annotations

from pathlib import Path

from common.result import Err, Ok, Result
from discovery import NodeKind, scan
from flows.commands import FlowCommandWriter, write_flow_command
from flows.models import Flow, FlowNode


class FakeWriter:
    def __init__(self, reply: Result[str, str]) -> None:
        self._reply = reply
        self.calls: list[tuple[Flow, str, Path]] = []

    def write(self, flow: Flow, *, command_name: str, flows_dir: Path) -> Result[str, str]:
        self.calls.append((flow, command_name, flows_dir))
        return self._reply


def _flow(name: str = "ship-feature") -> Flow:
    return Flow(
        name=name,
        description="plan, build, and verify",
        nodes=(FlowNode(id="plan", ref="agent:planner"),),
    )


def _valid_markdown(description: str = "Run ship-feature") -> str:
    return f"---\ndescription: {description}\nallowed-tools: Bash, PowerShell\nshell: powershell\ndisable-model-invocation: true\n---\n\n```!\nuv run python main.py --run-flow 'ship-feature'\n```\n"


def test_write_flow_command_uses_writer_output_and_is_discoverable(tmp_path: Path) -> None:
    claude_root = tmp_path / ".claude"
    commands_dir = claude_root / "commands"
    flows_dir = tmp_path / ".devinci" / "flows"
    writer = FakeWriter(Ok(_valid_markdown()))

    result = write_flow_command(_flow(), commands_dir, flows_dir=flows_dir, writer=writer)

    assert isinstance(result, Ok)
    assert result.value == commands_dir / "ship-feature.md"
    assert result.value.read_text(encoding="utf-8") == _valid_markdown()
    assert writer.calls == [(_flow(), "ship-feature", flows_dir)]
    discovered = scan((claude_root,)).find(NodeKind.COMMAND, "ship-feature")
    assert discovered is not None
    assert discovered.description == "Run ship-feature"


def test_write_flow_command_falls_back_when_crewai_output_is_invalid(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    flows_dir = tmp_path / ".devinci" / "flows"
    writer = FakeWriter(Ok("not a claude command"))

    result = write_flow_command(_flow(), commands_dir, flows_dir=flows_dir, writer=writer)

    assert isinstance(result, Ok)
    text = result.value.read_text(encoding="utf-8")
    assert text.startswith("---\ndescription: Run DeVinci flow 'ship-feature'")
    assert "--run-flow 'ship-feature'" in text
    assert f"--flows-dir '{flows_dir}'" in text


def test_write_flow_command_rejects_unusable_flow_name(tmp_path: Path) -> None:
    result = write_flow_command(
        _flow("///"),
        tmp_path / ".claude" / "commands",
        flows_dir=tmp_path / ".devinci" / "flows",
    )

    assert isinstance(result, Err)
    assert "command name" in result.error


def test_command_writer_protocol_is_structural() -> None:
    assert isinstance(FakeWriter(Ok(_valid_markdown())), FlowCommandWriter)
