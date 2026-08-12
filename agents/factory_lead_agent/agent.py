from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task
from typing import Any
from agents.agent_settings import AgentConfig


@CrewBase
class FactoryLeadAgent(AgentConfig):

    @agent
    def factory_lead(self) -> Agent:
        return Agent(config=self.agents_config["factory_lead"], llm=self.llm)

    @task
    def create_agent_task(self, **kwargs: Any) -> Task:
        return Task(config=self.tasks_config["create_agent_task"], agent=self.factory_lead(), **kwargs)

    @crew
    def crew(self) -> Crew:
        """Create the factory lead crew."""
        return Crew(agents=self.agents, tasks=self.tasks, skills=["./skills"])
