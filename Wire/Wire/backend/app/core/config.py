"""Settings for the single Wire backend.

Everything is read from environment variables or from `backend/.env`
(created by `setup.bat`). On Render the values come from the dashboard.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _is_secure_postgres(url: str) -> bool:
    return (
        url.startswith("postgresql+psycopg://")
        and make_url(url).query.get("sslmode") == "verify-full"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("WIRE_ENV_FILE", str(BACKEND_DIR / ".env")),
        extra="ignore",
    )
    environment: str = "development"
    # Login used by the account/social half of the API (wire_main_backend).
    database_url: str = "sqlite:///./wire-dev.db"
    # Login used by the chat half of the API (wire_chat_backend). The two Supabase
    # roles stay separate, exactly as before. Empty means "same as DATABASE_URL",
    # which is only allowed for local SQLite development.
    chat_database_url: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,10.0.2.2,testserver"
    session_days: int = 7
    rate_limits_enabled: bool = True
    email_code_pepper: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    minimum_age: int = 13

    @property
    def chat_url(self) -> str:
        return self.chat_database_url or self.database_url

    @property
    def host_list(self) -> list[str]:
        hosts = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        # Render injects the service's own public hostname automatically.
        render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
        if render_host and render_host not in hosts:
            hosts.append(render_host)
        return hosts

    @model_validator(mode="after")
    def production_requirements(self):
        if self.environment not in ("development", "production", "test"):
            raise ValueError("Unknown environment")
        if not 1 <= self.session_days <= 30:
            raise ValueError("SESSION_DAYS must be between 1 and 30")
        if self.environment == "production":
            if not _is_secure_postgres(self.database_url):
                raise ValueError(
                    "Production requires PostgreSQL with sslmode=verify-full"
                )
            if not self.chat_database_url or not _is_secure_postgres(
                self.chat_database_url
            ):
                raise ValueError(
                    "Production requires CHAT_DATABASE_URL: PostgreSQL with "
                    "sslmode=verify-full for the chat database login"
                )
            if not self.rate_limits_enabled or "*" in self.allowed_hosts:
                raise ValueError(
                    "Production requires enabled rate limits and explicit allowed hosts"
                )
        return self


@lru_cache
def settings():
    return Settings()
