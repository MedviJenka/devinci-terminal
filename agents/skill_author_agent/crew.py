"""Runnable entrypoint for the skill author CrewAI package."""

from __future__ import annotations

from common.result import Err, Ok, Result
from agents.skill_author_agent.agent import SkillAuthorAgent

__all__ = ["skill_author"]


def skill_author(description: str) -> Result[str, str]:
    """Run the SkillAuthorAgent crew and return its Markdown output."""
    description = description.strip()
    if not description:
        return Err("description must not be empty")
    try:
        output = SkillAuthorAgent().crew().kickoff(inputs={"description": description})
    except Exception as exc:
        return Err(f"skill author failed: {exc}")
    text = getattr(output, "raw", None) or str(output)
    text = text.strip()
    return Ok(text) if text else Err("skill author produced empty output")
