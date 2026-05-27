"""App configuration loaded from environment variables.

This module is intentionally small: it loads settings once at import time and
re-exports a `settings` singleton. All DB / migration code reads from here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed environment config.

    Required env vars:
      - DATABASE_URL          (e.g. postgresql+psycopg://user:pass@host:5432/db)
      - JWT_SECRET            (>= 32 chars)

    Optional env vars have sensible defaults below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- database ---
    database_url: str = Field(
        default="postgresql+psycopg://energyops:changeme_postgres@localhost:5432/energyops",
        alias="DATABASE_URL",
    )

    # --- jwt / auth ---
    jwt_secret: str = Field(
        default="dev_only_secret_replace_me_with_a_long_random_string_32+",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")

    # --- cors / logging ---
    cors_origins_raw: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- seed users (read by scripts/seed.py) ---
    seed_admin_email: str = Field(default="admin@example.com", alias="SEED_ADMIN_EMAIL")
    seed_admin_password: str = Field(default="admin123", alias="SEED_ADMIN_PASSWORD")
    seed_manager_email: str = Field(default="manager@example.com", alias="SEED_MANAGER_EMAIL")
    seed_manager_password: str = Field(default="manager123", alias="SEED_MANAGER_PASSWORD")
    seed_engineer_email: str = Field(default="engineer@example.com", alias="SEED_ENGINEER_EMAIL")
    seed_engineer_password: str = Field(default="engineer123", alias="SEED_ENGINEER_PASSWORD")
    seed_operator_email: str = Field(default="operator@example.com", alias="SEED_OPERATOR_EMAIL")
    seed_operator_password: str = Field(default="operator123", alias="SEED_OPERATOR_PASSWORD")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origins(self) -> List[str]:
        """Parse `CORS_ORIGINS` as a comma-separated list."""
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Sync URL used by Alembic + the seed script.

        The runtime app may use an async driver later; for migrations and
        seeding we keep things simple with the plain `psycopg` driver.
        """
        url = self.database_url
        # Normalise common async prefixes back to sync for Alembic.
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
