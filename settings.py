from pydantic import Field
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class _Config(BaseSettings):

    model_config = SettingsConfigDict(extra='allow', env_file='.env')

    PROVIDER:          str           = Field(default='anthropic')
    MODEL:             str           = Field(default='anthropic/claude-opus-4-8')
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_KEY:    Optional[str] = Field(default=None)
    VERBOSE:           bool          = Field(default=False)

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
