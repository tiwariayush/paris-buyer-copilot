"""Centralised configuration loaded from environment + .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings:
    duckdb_path: Path = Path(os.getenv("DUCKDB_PATH", str(ROOT / "data" / "paris.duckdb")))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    idfm_token: str | None = os.getenv("IDFM_TOKEN")
    cors_origins: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000"
    ).split(",")
    user_agent: str = os.getenv(
        "USER_AGENT",
        "ParisBuyerCopilot/0.1 (+https://github.com/local; contact@example.com)",
    )
    request_timeout_s: float = float(os.getenv("REQUEST_TIMEOUT_S", "20"))


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
