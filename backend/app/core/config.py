from typing import List, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    # Kept for backwards compatibility with the initial application settings.
    # Authentication uses JWT_SECRET below.
    SECRET_KEY: str = "change-this-to-a-super-secret-key-in-production"

    # Authentication
    JWT_SECRET: str = "change-this-jwt-secret-in-production"
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=1,
        validation_alias=AliasChoices(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        ),
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        ge=1,
        validation_alias=AliasChoices(
            "REFRESH_TOKEN_EXPIRE_DAYS",
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        ),
    )
    AUTH_RATE_LIMIT: int = Field(default=5, ge=0)
    AUTH_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1)

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://catalyst:catalyst@localhost:5432/catalyst_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # API
    API_V1_STR: str = "/api/v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
