from pathlib import Path
import os
from functools import lru_cache

import certifi
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
TEMPLATES_DIR = PACKAGE_DIR / "templates"


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ivygpt",
        alias="DATABASE_URL"
    )
    gemini_model: str | None = Field(default=None, alias="GEMINI_MODEL")
    google_model: str | None = Field(default=None, alias="GOOGLE_MODEL")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="qwen/qwen3.8-27b:free", alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    cors_allow_origins: str = Field(default="*", alias="CORS_ALLOW_ORIGINS")
    app_base_url: str = Field(default="http://localhost:8080", alias="APP_BASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    jwt_secret_key: str = Field(default="change-this-secret-key", alias="JWT_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    otp_expire_minutes: int = Field(default=10, alias="OTP_EXPIRE_MINUTES")
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="no-reply@ivygpt.local", alias="SMTP_FROM_EMAIL")
    smtp_from_name: str | None = Field(default=None, alias="SMTP_FROM_NAME")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    mcp_config_path: str = Field(default="mcp_servers.json", alias="MCP_CONFIG_PATH")
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_send_default_pii: bool = Field(default=True, alias="SENTRY_SEND_DEFAULT_PII")
    sentry_enable_logs: bool = Field(default=True, alias="SENTRY_ENABLE_LOGS")
    sentry_traces_sample_rate: float = Field(default=1.0, alias="SENTRY_TRACES_SAMPLE_RATE")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def default_model(self) -> str:
        return self.openrouter_model

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("sqlite"):
            raise ValueError("SQLite is no longer supported. Set DATABASE_URL to a PostgreSQL URL.")

        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

        return self.database_url

    @property
    def postgres_checkpoint_url(self) -> str:
        return self.async_database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    @property
    def cors_origins(self) -> list[str]:
        if self.cors_allow_origins.strip() == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def apply_runtime_environment() -> None:
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)

    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)

    if settings.tavily_api_key:
        os.environ.setdefault("TAVILY_API_KEY", settings.tavily_api_key)


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    CHROMA_DIR.mkdir(exist_ok=True)
