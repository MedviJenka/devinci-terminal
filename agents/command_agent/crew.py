from collections.abc import Mapping
from typing import Any

from common.result import Result
from agents.crew_runner import kickoff_raw
from agents.command_agent.agent import CommandAgent


def command_agent(inputs: str | Mapping[str, Any]) -> Result[str, str]:
    return kickoff_raw(lambda: CommandAgent().crew(), inputs)
