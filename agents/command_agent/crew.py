"""Runnable entrypoint for the command writer CrewAI package."""

from __future__ import annotations

from common.result import Err, Ok, Result
from agents.command_agent.agent import CommandAgent

__all__ = ["command_agent"]


def command_agent(description: str) -> Result[str, str]:
    """Run the CommandAgent crew and return its Markdown output."""
    return _kickoff(CommandAgent, description)


def _kickoff(agent_type: type[CommandAgent], description: str) -> Result[str, str]:
    description = description.strip()
    if not description:
        return Err("description must not be empty")
    try:
        output = agent_type().crew().kickoff(inputs={"description": description})
    except Exception as exc:  # CrewAI/LLM boundary: convert throws to Result.
        return Err(f"command agent failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    return Ok(text) if text else Err("command agent produced empty output")
