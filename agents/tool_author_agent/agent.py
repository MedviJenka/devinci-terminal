from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task
from typing import Any
from agents.agent_settings import AgentConfig


@CrewBase
class ToolAuthorAgent(AgentConfig):

    @agent
    def tool_author(self) -> Agent:
        return Agent(config=self.agents_config["tool_author"], llm=self.llm)

    @task
    def create_tool_task(self, **kwargs: Any) -> Task:
        return Task(config=self.tasks_config["create_tool_task"], agent=self.tool_author(), **kwargs)

    @crew
    def crew(self) -> Crew:
        """Create the tool author crew."""
        return Crew(agents=self.agents, tasks=self.tasks, skills=["./skills"])
