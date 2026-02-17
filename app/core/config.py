from functools import lru_cache
from typing import Optional

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
    saxo_base_url: str = Field(
        default="https://gateway.saxobank.com/sim",
        alias="SAXO_BASE_URL",
    )
    saxo_access_token: Optional[str] = Field(default=None, alias="SAXO_ACCESS_TOKEN")
    saxo_csv_dir: Optional[str] = Field(default=None, alias="SAXO_CSV_DIR")
    lunar_base_url: str = Field(
        default="https://openbanking.prod.lunar.app/aisp-pisp",
        alias="LUNAR_BASE_URL",
    )
    lunar_access_token: Optional[str] = Field(default=None, alias="LUNAR_ACCESS_TOKEN")
    lunar_csv_dir: Optional[str] = Field(default=None, alias="LUNAR_CSV_DIR")
    lunar_device_id: str = Field(default="finance-agents", alias="LUNAR_DEVICE_ID")
    lunar_os: str = Field(default="linux", alias="LUNAR_OS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
