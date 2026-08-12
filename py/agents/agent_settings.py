from typing import Generic, TypeVar
from crewai import Agent, LLM
from pydantic import BaseModel
from settings import Config
from dataclasses import dataclass


__all__ = ["AgentSettings", "SingleAgent"]

T = TypeVar("T", bound=BaseModel)


class AgentSettings:
    """Mixin that provides a configured LLM instance."""

    @property
    def llm(self) -> LLM:
        return LLM(model=Config.OPENAI_MODEL, api_key=Config.OPENAI_API_KEY)



@dataclass
class SingleAgent(Generic[T], AgentSettings):

    role: str
    goal: str
    backstory: str

    async def run(self, prompt: str) -> dict:
        response = Agent(role=self.role, goal=self.goal, backstory=self.backstory, llm=self.llm)
        return await response.akickoff(messages=prompt, response_format=T)


if __name__ == '__main__':
    agent = SingleAgent(role='funny', goal='funny', backstory='funny')
    agent.run('devops joke')

