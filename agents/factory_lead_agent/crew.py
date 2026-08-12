from collections.abc import Mapping
from typing import Any

from common.result import Result
from agents.crew_runner import kickoff_raw
from agents.factory_lead_agent.agent import FactoryLeadAgent


def factory_lead(inputs: str | Mapping[str, Any]) -> Result[str, str]:
    return kickoff_raw(lambda: FactoryLeadAgent().crew(), inputs)
