"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve to <repo-root>/.env regardless of the process CWD.
# This file lives at apps/api/src/api/config.py (4 levels deep).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="postgresql+asyncpg://retrace:retrace_dev@localhost:5432/retrace",
        alias="DATABASE_URL",
    )

    clickhouse_host: str = Field(default="localhost", alias="CLICKHOUSE_HOST")
    clickhouse_http_port: int = Field(default=8123, alias="CLICKHOUSE_HTTP_PORT")
    clickhouse_native_port: int = Field(default=9000, alias="CLICKHOUSE_NATIVE_PORT")
    clickhouse_user: str = Field(default="retrace", alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field(default="retrace_dev", alias="CLICKHOUSE_PASSWORD")
    clickhouse_database: str = Field(default="retrace", alias="CLICKHOUSE_DATABASE")

    api_secret_key: str = Field(default="change_me_in_production", alias="API_SECRET_KEY")
    api_env: str = Field(default="development", alias="API_ENV")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
