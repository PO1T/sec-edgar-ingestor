from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


def _load_dotenv_if_available(dotenv_path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)


def _get_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _get_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _get_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean")


@dataclass(frozen=True)
class Settings:
    db_dsn: str | None
    user_agent: str | None
    data_dir: Path
    log_level: str
    requests_per_second: float
    http_timeout_seconds: float
    embeddings_enabled: bool
    embedding_api_url: str
    embedding_api_key: str | None
    embedding_profile_name: str
    embedding_model: str
    embedding_dimensions: int
    embedding_batch_size: int
    embedding_timeout_seconds: float
    embedding_max_retries: int

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path = ".env",
    ) -> "Settings":
        env_path = Path(env_file)
        _load_dotenv_if_available(env_path)

        source = dict(os.environ if env is None else env)
        data_dir = Path(source.get("SEC_EDGAR_DATA_DIR", "./data")).expanduser()

        return cls(
            db_dsn=source.get("SEC_EDGAR_DB_DSN"),
            user_agent=source.get("SEC_EDGAR_USER_AGENT"),
            data_dir=data_dir,
            log_level=source.get("SEC_EDGAR_LOG_LEVEL", "INFO").upper(),
            requests_per_second=_get_float(
                source,
                "SEC_EDGAR_REQUESTS_PER_SECOND",
                5.0,
            ),
            http_timeout_seconds=_get_float(
                source,
                "SEC_EDGAR_HTTP_TIMEOUT_SECONDS",
                30.0,
            ),
            embeddings_enabled=_get_bool(
                source,
                "SEC_EDGAR_EMBEDDINGS_ENABLED",
                False,
            ),
            embedding_api_url=source.get(
                "SEC_EDGAR_EMBEDDING_API_URL",
                "https://api.openai.com/v1/embeddings",
            ),
            embedding_api_key=source.get("SEC_EDGAR_EMBEDDING_API_KEY") or None,
            embedding_profile_name=source.get(
                "SEC_EDGAR_EMBEDDING_PROFILE",
                "default",
            ),
            embedding_model=source.get(
                "SEC_EDGAR_EMBEDDING_MODEL",
                "text-embedding-3-small",
            ),
            embedding_dimensions=_get_int(
                source,
                "SEC_EDGAR_EMBEDDING_DIMENSIONS",
                1536,
            ),
            embedding_batch_size=_get_int(
                source,
                "SEC_EDGAR_EMBEDDING_BATCH_SIZE",
                64,
            ),
            embedding_timeout_seconds=_get_float(
                source,
                "SEC_EDGAR_EMBEDDING_TIMEOUT_SECONDS",
                60.0,
            ),
            embedding_max_retries=_get_int(
                source,
                "SEC_EDGAR_EMBEDDING_MAX_RETRIES",
                3,
            ),
        )

    def require_db(self) -> str:
        if not self.db_dsn:
            raise ConfigurationError("SEC_EDGAR_DB_DSN is required")
        return self.db_dsn

    def require_user_agent(self) -> str:
        if not self.user_agent:
            raise ConfigurationError("SEC_EDGAR_USER_AGENT is required")
        return self.user_agent
