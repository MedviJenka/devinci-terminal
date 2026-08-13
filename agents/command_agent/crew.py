"""Runnable entrypoint for the command writer CrewAI package."""

from __future__ import annotations

from common.logging import get_logger
from common.result import Err, Ok, Result
from agents.command_agent.agent import CommandAgent

__all__ = ["command_agent"]

logger = get_logger(__name__)


def command_agent(description: str) -> Result[str, str]:
    """Run the CommandAgent crew and return its Markdown output."""
    return _kickoff(CommandAgent, description)


def _kickoff(agent_type: type[CommandAgent], description: str) -> Result[str, str]:
    description = description.strip()
    if not description:
        logger.warning("command_agent_rejected", reason="empty description")
        return Err("description must not be empty")
    logger.info("command_agent_started", description_len=len(description))
    try:
        output = agent_type().crew().kickoff(inputs={"description": description})
    except Exception as exc:  # CrewAI/LLM boundary: convert throws to Result.
        logger.error("command_agent_crashed", error=str(exc))
        return Err(f"command agent failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    if not text:
        logger.warning("command_agent_empty_output")
        return Err("command agent produced empty output")
    logger.info("command_agent_succeeded", output_len=len(text))
    return Ok(text)
