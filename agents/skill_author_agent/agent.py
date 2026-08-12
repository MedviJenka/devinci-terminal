from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task
from typing import Any
from agents.agent_settings import AgentConfig


@CrewBase
class SkillAuthorAgent(AgentConfig):

    @agent
    def skill_author(self) -> Agent:
        return Agent(config=self.agents_config["skill_author"], llm=self.llm)

    @task
    def create_skill_task(self, **kwargs: Any) -> Task:
        return Task(config=self.tasks_config["create_skill_task"], agent=self.skill_author(), **kwargs)

    @crew
    def crew(self) -> Crew:
        """Create the skill author crew."""
        return Crew(agents=self.agents, tasks=self.tasks, skills=["./skills"])
