"""Neighborhood enrichment: schools nearby + IRIS context (best-effort).

Schools come from data.education.gouv.fr (Annuaire de l'éducation), a
public Opendatasoft dataset that supports lat/lon queries. We don't fail
the request if these calls error — neighborhood is decoration, not core.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings
from ..models.schemas import Neighborhood
from .cache import get_cache

EDU_API = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-en-annuaire-education/records"
)


async def _schools_near(
    lat: float, lon: float, radius_m: int = 700, postcode: str | None = None
) -> list[dict[str, Any]]:
    """Schools near a point. Tries spatial filter first; falls back to postcode."""
    cfg = settings()
    out: list[dict[str, Any]] = []

    async def _fetch(params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(
                timeout=cfg.request_timeout_s,
                headers={"User-Agent": cfg.user_agent},
            ) as client:
                resp = await client.get(EDU_API, params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except httpx.HTTPError:
            return []
        rows: list[dict[str, Any]] = []
        for r in data.get("results") or []:
            pos = r.get("position") or {}
            rows.append(
                {
                    "name": r.get("nom_etablissement"),
                    "type": r.get("type_etablissement"),
                    "nature": r.get("nature_uai_libe"),
                    "city": r.get("libelle_commune"),
                    "lat": pos.get("lat") or pos.get("lat"),
                    "lon": pos.get("lon") or pos.get("lon"),
                }
            )
        return rows

    # Strategy 1: spatial filter via ODSQL (works on most Opendatasoft datasets).
    spatial_params = {
        "where": (
            f"within_distance(position, GEOM'POINT({lon} {lat})', {radius_m}m)"
        ),
        "limit": 10,
        "order_by": "nom_etablissement",
    }
    out = await _fetch(spatial_params)
    if out:
        return out

    # Strategy 2: postcode fallback.
    if postcode:
        out = await _fetch({"where": f"code_postal_uai='{postcode}'", "limit": 12})
    return out


async def enrich(
    lat: float | None,
    lon: float | None,
    iris_code: str | None,
    iris_name: str | None,
    postcode: str | None = None,
) -> Neighborhood:
    if lat is None or lon is None:
        return Neighborhood(iris_code=iris_code, iris_name=iris_name)
    cache = get_cache()
    cache_key = f"nbh:{round(lat, 5)},{round(lon, 5)}"
    cached = await cache.get(cache_key)
    if cached:
        try:
            return Neighborhood(**json.loads(cached))
        except Exception:
            pass
    schools = await _schools_near(lat, lon, postcode=postcode)
    nbh = Neighborhood(
        iris_code=iris_code,
        iris_name=iris_name,
        nearest_schools=schools,
    )
    await cache.set(cache_key, nbh.model_dump_json(), ttl=86400)
    return nbh
