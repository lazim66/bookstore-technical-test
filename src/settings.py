"""Application settings using Pydantic Settings."""

from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["LOCAL", "TEST"] = "LOCAL"
    LOGGING_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_POOL_SIZE: int = 20
    DATABASE_POOL_SIZE_OVERFLOW: int = 40

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # Session
    SESSION_EXPIRE_MINUTES: int = 30

    # Seed Admin
    SEED_ADMIN_EMAIL: str = "admin@bookstore.com"
    SEED_ADMIN_PASSWORD: str = "admin123secure"
    SEED_ADMIN_FULL_NAME: str = "System Admin"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
