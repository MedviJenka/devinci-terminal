"""Runnable entrypoint for the factory lead CrewAI package."""

from __future__ import annotations

from common.logging import get_logger
from common.result import Err, Ok, Result
from agents.factory_lead_agent.agent import FactoryLeadAgent

__all__ = ["factory_lead"]

logger = get_logger(__name__)


def factory_lead(description: str) -> Result[str, str]:
    """Run the FactoryLeadAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        logger.warning("factory_lead_rejected", reason="empty description")
        return Err("description must not be empty")
    logger.info("factory_lead_started", description_len=len(description))
    try:
        output = FactoryLeadAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        logger.error("factory_lead_crashed", error=str(exc))
        return Err(f"factory lead failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    if not text:
        logger.warning("factory_lead_empty_output")
        return Err("factory lead produced empty output")
    logger.info("factory_lead_succeeded", output_len=len(text))
    return Ok(text)
