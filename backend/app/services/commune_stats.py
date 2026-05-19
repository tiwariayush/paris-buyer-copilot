"""Commune-level stats from geo.api.gouv.fr (free, no API key)."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings
from .cache import get_cache

log = logging.getLogger(__name__)

GEO_API = "https://geo.api.gouv.fr"


async def fetch_commune(code_commune: str) -> dict[str, Any]:
    """Population and name for a Paris arrondissement INSEE code (e.g. 75111)."""
    if not code_commune:
        return {}
    cache = get_cache()
    key = f"commune:{code_commune}"
    cached = await cache.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    cfg = settings()
    url = f"{GEO_API}/communes/{code_commune}"
    try:
        async with httpx.AsyncClient(
            timeout=cfg.request_timeout_s,
            headers={"User-Agent": cfg.user_agent},
        ) as client:
            resp = await client.get(
                url,
                params={"fields": "nom,code,population,codesPostaux"},
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
    except httpx.HTTPError as e:
        log.warning("commune_api_failed code=%s err=%s", code_commune, str(e)[:120])
        return {}

    out = {
        "name": data.get("nom"),
        "population": data.get("population"),
    }
    await cache.set(key, json.dumps(out), ttl=86400 * 7)
    return out
