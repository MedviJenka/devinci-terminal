from collections.abc import Mapping
from typing import Any

from common.result import Result
from agents.crew_runner import kickoff_raw
from agents.skill_author_agent.agent import SkillAuthorAgent


def skill_author(inputs: str | Mapping[str, Any]) -> Result[str, str]:
    return kickoff_raw(lambda: SkillAuthorAgent().crew(), inputs)
