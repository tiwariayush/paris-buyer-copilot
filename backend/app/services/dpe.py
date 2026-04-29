"""Energy performance lookup via the public DPE Logements existants API.

Open data, refreshed weekly. We search by address and (when available)
postcode, then keep the most recent record.

Endpoint: https://data.ademe.fr/data-fair/api/v1/datasets/dpe-v2-logements-existants/lines
(also mirrored at data.gouv.fr; we hit the ADEME Data-Fair API directly,
which is what the official portal uses.)
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import settings
from ..models.schemas import DPEReport
from .cache import get_cache

DPE_API = (
    "https://data.ademe.fr/data-fair/api/v1/datasets/"
    "meg-83tjwtg8dyz4vv7h1dqe/lines"
)


def _pick_class(rec: dict[str, Any], key: str = "etiquette_dpe") -> str | None:
    v = rec.get(key)
    if isinstance(v, str) and v:
        return v.strip().upper()[:1]
    return None


def _to_float(x: Any) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def lookup(
    address: str | None,
    postcode: str | None = None,
    *,
    surface: float | None = None,
) -> DPEReport | None:
    if not address:
        return None
    cache = get_cache()
    cache_key = f"dpe:{postcode or ''}:{address.lower()[:120]}"
    cached = await cache.get(cache_key)
    if cached:
        try:
            return DPEReport(**json.loads(cached))
        except Exception:
            pass

    cfg = settings()
    q_parts = [address]
    if postcode:
        q_parts.append(postcode)
    params: dict[str, Any] = {
        "q": " ".join(q_parts),
        "size": 5,
        "sort": "-date_etablissement_dpe",
        "select": (
            "etiquette_dpe,etiquette_ges,"
            "conso_5_usages_par_m2_ef,"
            "emission_ges_5_usages_par_m2,"
            "surface_habitable_logement,"
            "date_etablissement_dpe,"
            "adresse_ban,code_postal_ban"
        ),
    }
    try:
        async with httpx.AsyncClient(
            timeout=cfg.request_timeout_s,
            headers={"User-Agent": cfg.user_agent},
        ) as client:
            resp = await client.get(DPE_API, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except httpx.HTTPError:
        return None

    results = data.get("results") or []
    if not results:
        return None
    # Prefer record whose surface is closest to the listing's, else newest.
    if surface:
        results.sort(
            key=lambda r: abs(
                (_to_float(r.get("surface_habitable_logement")) or 1e6)
                - surface
            )
        )
    rec = results[0]
    year = None
    d = rec.get("date_etablissement_dpe")
    if isinstance(d, str) and len(d) >= 4:
        try:
            year = int(d[:4])
        except ValueError:
            year = None
    report = DPEReport(
        dpe_class=_pick_class(rec),
        ges_class=(rec.get("etiquette_ges") or "").upper()[:1] or None,
        consumption_kwh_m2_year=_to_float(rec.get("conso_5_usages_par_m2_ef")),
        emissions_kgco2_m2_year=_to_float(rec.get("emission_ges_5_usages_par_m2")),
        surface_m2=_to_float(rec.get("surface_habitable_logement")),
        year_certified=year,
        address=rec.get("adresse_ban"),
    )
    await cache.set(cache_key, report.model_dump_json(), ttl=86400 * 7)
    return report
