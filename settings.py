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


Config = load_config()
