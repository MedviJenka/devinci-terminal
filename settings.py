from pydantic import Field
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Config(BaseSettings):

    model_config = SettingsConfigDict(extra='allow', env_file='.env')

    MODEL:             str  = Field(...)
    OPENAI_API_KEY:    str  = Field(...)
    ANTHROPIC_API_KEY: str  = Field(default=None)
    VERBOSE:           bool = Field(default=False)


@lru_cache
def load_config() -> _Config:
    return _Config()


class _ConfigProxy:
    """Lazy settings proxy so importing modules does not require API keys."""

    def __getattr__(self, name: str) -> object:
        return getattr(load_config(), name)


Config = _ConfigProxy()
