import inspect
import yaml
from pathlib import Path
from typing import Any, Protocol
from crewai import Agent, LLM
from functools import cached_property

from settings import Config as _DefaultConfig
from common.result import Result, Ok, Err

__all__ = ["SingleAgentFactory", "ConfigLike"]


class ConfigLike(Protocol):
    """The settings surface SingleAgentFactory depends on (injectable for tests)."""

    MODEL: str
    VERBOSE: bool

    @property
    def api_key(self) -> str | None: ...


class SingleAgentFactory:
    """Builds and runs a single CrewAI agent from a YAML config entry.

    Config is injected so the factory targets a runtime interface, not a global
    singleton — pass a stub ConfigLike (and optionally a prebuilt LLM) in tests.
    """

    def __init__(
        self,
        config_dir: Path,
        config: ConfigLike | None = None,
        llm: LLM | None = None,
    ) -> None:
        self._config: ConfigLike = config or _DefaultConfig
        self._injected_llm = llm
        self._agents_config: dict[str, Any] = self._load_yaml(config_dir / "agents.yaml")

    @cached_property
    def llm(self) -> LLM:
        if self._injected_llm is not None:
            return self._injected_llm
        return LLM(model=self._config.MODEL, api_key=self._config.api_key)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    @staticmethod
    def _compose_prompt(inputs: str | dict[str, Any]) -> Result[str, str]:
        """Turn a string or a {context, query} dict into a single user prompt."""
        if isinstance(inputs, str):
            prompt = inputs.strip()
            return Ok(prompt) if prompt else Err("inputs string must not be empty")

        parts: list[str] = []
        if inputs.get("context"):
            parts.append(f"Context:\n{inputs['context']}")
        if inputs.get("query"):
            parts.append(str(inputs["query"]))
        if not parts:
            return Err("inputs dict must contain a non-empty 'context' or 'query'")
        return Ok("\n\n".join(parts))

    def run(
        self,
        agent_name: str,
        inputs: str | dict[str, Any],
        skills: list[str],
    ) -> Result[str, str]:
        if agent_name not in self._agents_config:
            return Err(f"unknown agent: {agent_name}")

        if self._config.api_key is None:
            return Err("no API key configured for the active provider")

        prompt = self._compose_prompt(inputs)
        if isinstance(prompt, Err):
            return prompt

        agent = Agent(
            config=self._agents_config[agent_name],
            llm=self.llm,
            verbose=self._config.VERBOSE,
            skills=skills,
            max_rpm=10,
            respect_context_window=True,
        )

        try:
            output = agent.kickoff(prompt.value)
        except Exception as exc:  # crewai/litellm raise a variety of error types
            return Err(f"agent kickoff failed: {exc}")

        # kickoff() returns a coroutine when called inside a running event loop.
        if inspect.iscoroutine(output):
            output.close()
            return Err("agent kickoff returned a coroutine — call from a sync context")

        raw = getattr(output, "raw", None)
        if not isinstance(raw, str):
            return Err("agent kickoff produced no textual output")
        return Ok(raw)
