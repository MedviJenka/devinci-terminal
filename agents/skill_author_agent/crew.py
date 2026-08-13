"""Runnable entrypoint for the skill author CrewAI package."""

from __future__ import annotations

from common.logging import get_logger
from common.result import Err, Ok, Result
from agents.skill_author_agent.agent import SkillAuthorAgent

__all__ = ["skill_author"]

logger = get_logger(__name__)


def skill_author(description: str) -> Result[str, str]:
    """Run the SkillAuthorAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        logger.warning("skill_author_rejected", reason="empty description")
        return Err("description must not be empty")
    logger.info("skill_author_started", description_len=len(description))
    try:
        output = SkillAuthorAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        logger.error("skill_author_crashed", error=str(exc))
        return Err(f"skill author failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    if not text:
        logger.warning("skill_author_empty_output")
        return Err("skill author produced empty output")
    logger.info("skill_author_succeeded", output_len=len(text))
    return Ok(text)
