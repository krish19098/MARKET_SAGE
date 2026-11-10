"""Application settings, loaded from environment variables (prefix ``MARKET_SAGE_``) or ``.env``.

Secrets are never given defaults that would work in production, and are never logged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARKET_SAGE_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./var/market_sage.db"
    data_dir: Path = Path("./var/data")

    # Execution policy: only paper trading is supported. Any other value is refused at startup.
    execution_mode: str = "paper"

    # Authentication (single user, personal use).
    auth_username: str = "owner"
    auth_password_hash: SecretStr | None = None  # argon2 hash; generate with `market-sage hash-password`
    auth_totp_secret: SecretStr | None = None
    jwt_secret: SecretStr = SecretStr("dev-only-insecure-secret-change-me")
    jwt_ttl_minutes: int = 12 * 60

    # Angel One SmartAPI (market data / read-only account access only).
    angel_api_key: SecretStr | None = None
    angel_client_code: str | None = None
    angel_pin: SecretStr | None = None
    angel_totp_secret: SecretStr | None = None

    # Web Push (VAPID).
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str = "mailto:owner@localhost"

    # Data freshness: maximum age (seconds) of live quotes before they are considered stale.
    live_stale_after_s: int = 120
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("execution_mode")
    @classmethod
    def _paper_only(cls, v: str) -> str:
        if v != "paper":
            raise ValueError("MARKET SAGE supports paper trading only; real-money execution is disabled by design.")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
