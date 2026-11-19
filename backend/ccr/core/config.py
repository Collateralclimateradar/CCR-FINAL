"""Application settings, read from environment variables (or a .env file)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Climate Guard AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # The login-free development routes are OFF unless this is explicitly true.
    # They are never enabled when environment is "production".
    enable_dev_routes: bool = False

    # Secret used to sign login tokens. There is no usable default on purpose:
    # login stays disabled until a secret of at least 32 characters is set.
    jwt_secret: str = ""
    jwt_expire_minutes: int = Field(default=30, ge=1, le=1440)

    # Required on purpose: there is no default, so no password lives in code.
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
