from pydantic import Field
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Config(BaseSettings):
    model_config = SettingsConfigDict(extra='allow', env_file='.env')

    # Claude-first: CrewAI-agent nodes target Anthropic through litellm's
    # `anthropic/` model prefix. Claude Code headless is the primary per-node
    # executor; this LLM path is the fallback runtime for CrewAI-agent nodes.
    PROVIDER: str = Field(default='anthropic')
    MODEL:    str = Field(default='anthropic/claude-opus-4-8')

    # Keys are optional so config always loads; the LLM boundary validates that
    # the active provider's key is present and returns a Result on failure.
    ANTHROPIC_API_KEY: str | None = Field(default=None)
    OPENAI_API_KEY:    str | None = Field(default=None)

    VERBOSE: bool = Field(default=False)

    @property
    def api_key(self) -> str | None:
        return (
            self.ANTHROPIC_API_KEY
            if self.PROVIDER == 'anthropic'
            else self.OPENAI_API_KEY
        )


@lru_cache
def load_config() -> _Config:
    return _Config()


Config = load_config()
