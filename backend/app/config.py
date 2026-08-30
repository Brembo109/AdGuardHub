"""Application settings, read from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADGUARDHUB_", extra="ignore")

    # Where the SQLite file lives. The Docker image mounts /data as a volume.
    data_dir: str = "./data"

    # Master secret. Used both for the session cookie signature and to derive the
    # Fernet key that encrypts instance credentials at rest. Never persisted to the DB.
    secret_key: str = ""

    # Optional bootstrap of the single admin account. When unset, the UI walks the
    # operator through a first-run setup instead.
    admin_username: str = ""
    admin_password: str = ""

    session_cookie: str = "adguardhub_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days

    # Background workers (seconds).
    reconcile_interval: int = 300
    retry_interval: int = 30
    querylog_poll_interval: int = 5
    querylog_buffer_size: int = 2000
    querylog_fetch_limit: int = 100

    http_timeout: float = 10.0

    # Serve the built frontend from this directory when it exists.
    static_dir: str = "./static"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir.rstrip('/')}/adguardhub.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
