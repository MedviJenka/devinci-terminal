"""Runnable entrypoint for the factory lead CrewAI package."""

from __future__ import annotations

from common.result import Err, Ok, Result
from agents.factory_lead_agent.agent import FactoryLeadAgent

__all__ = ["factory_lead"]


def factory_lead(description: str) -> Result[str, str]:
    """Run the FactoryLeadAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        return Err("description must not be empty")
    try:
        output = FactoryLeadAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        return Err(f"factory lead failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    return Ok(text) if text else Err("factory lead produced empty output")
