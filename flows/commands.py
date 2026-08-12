"""Claude slash-command authoring for saved DeVinci flows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from common.result import Err, Ok, Result
from discovery.frontmatter import parse_frontmatter
from flows.models import Flow

__all__ = [
    "FlowCommandWriter",
    "CrewAICommandWriter",
    "build_flow_command_markdown",
    "write_flow_command",
]

_SLUG_CHARS = re.compile(r"[^a-z0-9-]+")
_SLUG_DASHES = re.compile(r"-+")


@runtime_checkable
class FlowCommandWriter(Protocol):
    """Produces Markdown for a Claude command that runs a saved flow."""

    def write(
        self, flow: Flow, *, command_name: str, flows_dir: Path
    ) -> Result[str, str]: ...


class CrewAICommandWriter:
    """Draft command Markdown through the command_writer CrewAI agent."""

    def write(self, flow: Flow, *, command_name: str, flows_dir: Path) -> Result[str, str]:
        try:
            from agents.command_agent import command_agent
        except (ImportError, OSError) as exc:
            return Err(f"command agent unavailable: {exc}")

        return command_agent(_command_request(flow, command_name, flows_dir))


def write_flow_command(
    flow: Flow,
    commands_dir: Path,
    *,
    flows_dir: Path,
    writer: FlowCommandWriter | None = None,
) -> Result[Path, str]:
    """Write `<commands_dir>/<flow>.md`; fall back if the CrewAI draft is invalid."""
    command_name = _command_name(flow.name)
    if not command_name:
        return Err(f"flow '{flow.name}' does not produce a usable command name")

    markdown = build_flow_command_markdown(flow, command_name=command_name, flows_dir=flows_dir)
    if writer is not None:
        drafted = writer.write(flow, command_name=command_name, flows_dir=flows_dir)
        if isinstance(drafted, Ok) and _is_valid_command_markdown(drafted.value):
            markdown = drafted.value

    try:
        commands_dir.mkdir(parents=True, exist_ok=True)
        path = commands_dir / f"{command_name}.md"
        path.write_text(_ensure_trailing_newline(markdown), encoding="utf-8")
        return Ok(path)
    except OSError as exc:
        return Err(f"could not write command '{command_name}': {exc}")


def build_flow_command_markdown(flow: Flow, *, command_name: str, flows_dir: Path) -> str:
    """Deterministic command body; used directly and as CrewAI validation fallback."""
    flow_name = _ps_quote(flow.name)
    flow_dir = _ps_quote(str(flows_dir))
    description = _yaml_single_line(f"Run DeVinci flow '{command_name}'")
    return (
        "---\n"
        f"description: {description}\n"
        "allowed-tools: Bash, PowerShell\n"
        "shell: powershell\n"
        "disable-model-invocation: true\n"
        "---\n\n"
        "```!\n"
        'if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "main.py")) {\n'
        '  if ((Split-Path -Leaf (Get-Location)) -eq "py") {\n'
        "    Set-Location ..\n"
        "  }\n"
        "}\n\n"
        "if (Get-Command uv -ErrorAction SilentlyContinue) {\n"
        f"  uv run python main.py --run-flow {flow_name} --flows-dir {flow_dir}\n"
        "} else {\n"
        f"  python main.py --run-flow {flow_name} --flows-dir {flow_dir}\n"
        "}\n"
        "```\n"
    )


def _command_request(flow: Flow, command_name: str, flows_dir: Path) -> str:
    steps = "\n".join(
        f"- {node.id}: run {node.ref} after {', '.join(node.after) or 'start'}"
        for node in flow.nodes
    )
    fallback = build_flow_command_markdown(flow, command_name=command_name, flows_dir=flows_dir)
    return (
        f"Create the Claude Code slash-command file for /{command_name}.\n"
        f"It must run the saved DeVinci flow named {flow.name!r}.\n"
        f"Flow description: {flow.description or '(none)'}\n"
        f"Saved flows directory: {flows_dir}\n"
        f"Flow steps:\n{steps}\n\n"
        "Output only the Markdown file. It must include YAML frontmatter with "
        "description, allowed-tools: Bash, PowerShell, shell: powershell, and "
        "disable-model-invocation: true. The body must be a dynamic ```! block. "
        "Use this exact executable command shape inside the block:\n\n"
        f"{fallback}"
    )


def _command_name(name: str) -> str:
    slug = _SLUG_CHARS.sub("-", name.strip().lower())
    slug = _SLUG_DASHES.sub("-", slug).strip("-")
    return slug


def _is_valid_command_markdown(text: str) -> bool:
    parsed = parse_frontmatter(text)
    if isinstance(parsed, Err):
        return False
    frontmatter, body = parsed.value
    return bool(str(frontmatter.get("description") or "").strip()) and "```!" in body


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _yaml_single_line(value: str) -> str:
    return value.replace("\n", " ")
