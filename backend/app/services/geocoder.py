"""Address geocoding via the French Base Adresse Nationale (BAN).

API doc: https://adresse.data.gouv.fr/api-doc/adresse
Endpoints:
- /search?q=...&limit=1   → forward geocoding (returns lat/lon, citycode...)
- /reverse?lon=..&lat=..  → reverse geocoding

Free, ~50 req/s. We cache results in Redis when available.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from ..config import settings
from ..models.schemas import GeoLocation
from .cache import get_cache

BAN_BASE = "https://api-adresse.data.gouv.fr"
CADASTRE_BASE = "https://apicarto.ign.fr/api/cadastre"


async def _ban_search(query: str, postcode: str | None = None) -> dict[str, Any] | None:
    cfg = settings()
    params: dict[str, Any] = {"q": query, "limit": 1, "autocomplete": 0}
    if postcode:
        params["postcode"] = postcode
    async with httpx.AsyncClient(
        timeout=cfg.request_timeout_s,
        headers={"User-Agent": cfg.user_agent},
    ) as client:
        resp = await client.get(f"{BAN_BASE}/search/", params=params)
        resp.raise_for_status()
        data = resp.json()
    feats = data.get("features") or []
    return feats[0] if feats else None


async def _cadastre_parcelle(
    lon: float, lat: float, citycode: str | None = None
) -> str | None:
    """Find the cadastral parcel ID at a coordinate, via api-carto IGN.

    DVF stores ``id_parcelle`` as ``{INSEE5}{section padded to 5}{numero padded to 4}``.
    For Paris, BAN's ``citycode`` is the arrondissement (e.g. ``75111``) which is
    what DVF uses, while api-carto returns the city-wide ``75056``. We prefer
    the BAN citycode whenever it's provided.
    """
    cfg = settings()
    geom = json.dumps({"type": "Point", "coordinates": [lon, lat]})
    try:
        async with httpx.AsyncClient(
            timeout=cfg.request_timeout_s,
            headers={"User-Agent": cfg.user_agent},
        ) as client:
            resp = await client.get(
                f"{CADASTRE_BASE}/parcelle",
                params={"geom": geom, "_limit": 1},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
    except httpx.HTTPError:
        return None
    feats = data.get("features") or []
    if not feats:
        return None
    p = feats[0].get("properties", {})
    code = (
        citycode
        or p.get("code_insee")
        or (p.get("code_dep", "") + p.get("code_com", ""))
    )
    section = p.get("section", "")
    numero = p.get("numero", "")
    if not (code and section and numero):
        return None
    section_padded = section.rjust(5, "0")[-5:]
    numero_padded = str(numero).rjust(4, "0")
    return f"{code}{section_padded}{numero_padded}"


async def _iris_lookup(lon: float, lat: float) -> tuple[str | None, str | None]:
    """Look up IRIS code at a lon/lat using Pyris (free)."""
    cfg = settings()
    try:
        async with httpx.AsyncClient(
            timeout=cfg.request_timeout_s,
            headers={"User-Agent": cfg.user_agent},
        ) as client:
            resp = await client.get(
                "https://pyris.datajazz.io/api/coords",
                params={"geolat": lat, "geolon": lon},
            )
            if resp.status_code != 200:
                return None, None
            data = resp.json()
    except httpx.HTTPError:
        return None, None
    if not data:
        return None, None
    return data.get("complete_code"), data.get("nom_iris")


async def geocode(
    address: str,
    postcode: str | None = None,
    *,
    fetch_iris: bool = True,
    fetch_parcelle: bool = True,
) -> GeoLocation | None:
    """Geocode an address; enrich with IRIS and parcelle when available."""
    cache = get_cache()
    cache_key = f"geo:{postcode or ''}:{address.lower()}"
    cached = await cache.get(cache_key)
    if cached:
        try:
            return GeoLocation(**json.loads(cached))
        except Exception:
            pass

    feat = await _ban_search(address, postcode)
    if not feat:
        return None
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [None, None])
    lon, lat = coords[0], coords[1]
    if lon is None or lat is None:
        return None
    props = feat.get("properties", {})
    code_commune = props.get("citycode", "")
    cp = props.get("postcode")

    iris_code = iris_name = parcelle = None
    if fetch_iris or fetch_parcelle:
        coros = []
        if fetch_iris:
            coros.append(_iris_lookup(lon, lat))
        if fetch_parcelle:
            coros.append(_cadastre_parcelle(lon, lat, citycode=code_commune))
        results = await asyncio.gather(*coros, return_exceptions=True)
        idx = 0
        if fetch_iris:
            r = results[idx]
            idx += 1
            if isinstance(r, tuple):
                iris_code, iris_name = r
        if fetch_parcelle:
            r = results[idx]
            if isinstance(r, str):
                parcelle = r

    loc = GeoLocation(
        lat=lat,
        lon=lon,
        address_normalized=props.get("label", address),
        score=props.get("score"),
        id_parcelle=parcelle,
        code_iris=iris_code,
        nom_iris=iris_name,
        code_commune=code_commune,
        code_postal=cp,
    )
    await cache.set(cache_key, loc.model_dump_json(), ttl=86400)
    return loc
