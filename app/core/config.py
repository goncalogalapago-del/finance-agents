from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_name: str = Field(default="finance-agents", alias="APP_NAME")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/finance_agents",
        alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    kill_switch_enabled: bool = Field(default=False, alias="KILL_SWITCH_ENABLED")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
