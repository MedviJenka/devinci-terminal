from crewai import LLM, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from dataclasses import dataclass
from functools import cached_property
from settings import Config


@dataclass
class AgentConfig:

    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config: dict = "config/agents.yaml"
    tasks_config: dict = "config/tasks.yaml"

    @cached_property
    def llm(self) -> LLM:
        return LLM(model=Config.MODEL, api_key=Config.OPENAI_API_KEY)
