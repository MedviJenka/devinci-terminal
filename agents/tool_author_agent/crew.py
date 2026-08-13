"""Runnable entrypoint for the tool author CrewAI package."""

from __future__ import annotations

from common.logging import get_logger
from common.result import Err, Ok, Result
from agents.tool_author_agent.agent import ToolAuthorAgent

__all__ = ["tool_author"]

logger = get_logger(__name__)


def tool_author(description: str) -> Result[str, str]:
    """Run the ToolAuthorAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        logger.warning("tool_author_rejected", reason="empty description")
        return Err("description must not be empty")
    logger.info("tool_author_started", description_len=len(description))
    try:
        output = ToolAuthorAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        logger.error("tool_author_crashed", error=str(exc))
        return Err(f"tool author failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    if not text:
        logger.warning("tool_author_empty_output")
        return Err("tool author produced empty output")
    logger.info("tool_author_succeeded", output_len=len(text))
    return Ok(text)
