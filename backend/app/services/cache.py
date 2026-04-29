"""Redis-backed cache with a graceful in-memory fallback.

Avoids a hard Redis dependency for local-only runs.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ..config import settings


class _MemoryCache:
    def __init__(self) -> None:
        self._d: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            row = self._d.get(key)
            if not row:
                return None
            exp, val = row
            if exp and exp < time.time():
                self._d.pop(key, None)
                return None
            return val

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            exp = time.time() + ttl if ttl else 0.0
            self._d[key] = (exp, value)


class _RedisCache:
    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("redis package not installed") from e
        self._client = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        try:
            if ttl:
                await self._client.set(key, value, ex=ttl)
            else:
                await self._client.set(key, value)
        except Exception:
            pass


_singleton: Any = None


def get_cache() -> Any:
    """Return a Redis-backed cache if reachable, else in-memory."""
    global _singleton
    if _singleton is not None:
        return _singleton
    cfg = settings()
    try:
        import redis  # noqa: F401
        client = _RedisCache(cfg.redis_url)
        _singleton = client
    except Exception:
        _singleton = _MemoryCache()
    return _singleton
