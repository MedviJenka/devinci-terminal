from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task
from typing import Any
from agents.agent_settings import AgentConfig


@CrewBase
class CommandAgent(AgentConfig):

    @agent
    def command_writer(self) -> Agent:
        return Agent(config=self.agents_config["command_writer"], llm=self.llm)

    @task
    def command_task(self, **kwargs: Any) -> Task:
        return Task(config=self.tasks_config["command_task"], agent=self.command_writer(), **kwargs)

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, skills=["./skills"])
