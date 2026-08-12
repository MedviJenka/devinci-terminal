"""Runnable entrypoint for the tool author CrewAI package."""

from __future__ import annotations

from common.result import Err, Ok, Result
from agents.tool_author_agent.agent import ToolAuthorAgent

__all__ = ["tool_author"]


def tool_author(description: str) -> Result[str, str]:
    """Run the ToolAuthorAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        return Err("description must not be empty")
    try:
        output = ToolAuthorAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        return Err(f"tool author failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    return Ok(text) if text else Err("tool author produced empty output")
