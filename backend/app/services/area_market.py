"""Address-level market statistics from DVF (multi-year, computed on demand).

Uses the ingested DuckDB mutations table — no paid API. For a listing we
aggregate apartment sales near the coordinates (≈600 m) and fall back to the
arrondissement when the micro-zone has too few transactions.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Literal

from ..db import cursor
from ..models.schemas import MarketIndex, YearlyMarketTrend

PARIS_PPM2_FLOOR = 4000
MIN_SALES_PER_YEAR = 5
DEFAULT_RADIUS_M = 600
DEFAULT_TYPE = "Appartement"


def _cos_deg(deg: float) -> float:
    return math.cos(math.radians(deg))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _spatial_where_clause(
    lon: float,
    lat: float,
    radius_m: int,
) -> tuple[str, list]:
    deg_lat = radius_m / 111_000
    deg_lon = radius_m / (111_000 * max(0.1, abs(_cos_deg(lat))))
    clause = """
        longitude IS NOT NULL AND latitude IS NOT NULL
        AND ABS(latitude - ?) < ?
        AND ABS(longitude - ?) < ?
        AND ST_Distance_Sphere(
            ST_Point(longitude, latitude),
            ST_Point(?, ?)
        ) <= ?
    """
    params = [lat, deg_lat, lon, deg_lon, lon, lat, radius_m]
    return clause, params


def yearly_trends(
    *,
    lon: float | None,
    lat: float | None,
    code_postal: str | None,
    radius_m: int = DEFAULT_RADIUS_M,
    type_local: str = DEFAULT_TYPE,
    min_year: int | None = None,
) -> tuple[list[YearlyMarketTrend], Literal["radius", "arrondissement"], str]:
    """Median €/m² and volume by calendar year for the micro-zone or arrondissement."""
    if min_year is None:
        min_year = date.today().year - 5

    scope: Literal["radius", "arrondissement"] = "radius"
    label = f"Rayon {radius_m} m"
    where_extra = ""
    params: list = [type_local, PARIS_PPM2_FLOOR, min_year]

    if lon is not None and lat is not None:
        spatial, spatial_params = _spatial_where_clause(lon, lat, radius_m)
        where_extra = f"AND {spatial}"
        params.extend(spatial_params)
    elif code_postal:
        scope = "arrondissement"
        label = f"Arrondissement {code_postal}"
        where_extra = "AND code_postal = ?"
        params.append(code_postal)
    else:
        return [], scope, label

    sql = f"""
        SELECT
            EXTRACT(year FROM date_mutation)::INTEGER AS yr,
            price_per_m2
        FROM mutations
        WHERE type_local = ?
          AND price_per_m2 >= ?
          AND EXTRACT(year FROM date_mutation) >= ?
          {where_extra}
    """
    with cursor() as cur:
        rows = cur.execute(sql, params).fetchall()

    by_year: dict[int, list[float]] = {}
    for yr, ppm2 in rows:
        if yr is None or ppm2 is None:
            continue
        by_year.setdefault(int(yr), []).append(float(ppm2))

    # If radius yields sparse data, retry at arrondissement level.
    if scope == "radius" and code_postal:
        recent_years = [y for y in by_year if y >= date.today().year - 2]
        thin = not recent_years or all(
            len(by_year.get(y, [])) < MIN_SALES_PER_YEAR for y in recent_years
        )
        if thin:
            return yearly_trends(
                lon=None,
                lat=None,
                code_postal=code_postal,
                radius_m=radius_m,
                type_local=type_local,
                min_year=min_year,
            )

    trends: list[YearlyMarketTrend] = []
    for yr in sorted(by_year):
        vals = by_year[yr]
        med = _median(vals)
        if med is None:
            continue
        trends.append(
            YearlyMarketTrend(
                year=yr,
                median_price_per_m2=round(med),
                transaction_count=len(vals),
            )
        )

    if scope == "arrondissement" and code_postal:
        label = f"Arrondissement {code_postal}"

    return trends, scope, label


def rolling_median_ppm2(
    *,
    lon: float | None,
    lat: float | None,
    code_postal: str | None,
    months: int = 12,
    radius_m: int = DEFAULT_RADIUS_M,
    type_local: str = DEFAULT_TYPE,
) -> tuple[float | None, int, Literal["radius", "arrondissement"]]:
    """Median €/m² over the last N months (same spatial logic as trends)."""
    cutoff = date.today().replace(day=1)
    # Approximate month rollback
    month = cutoff.month - months
    year = cutoff.year
    while month <= 0:
        month += 12
        year -= 1
    cutoff = cutoff.replace(year=year, month=month)

    scope: Literal["radius", "arrondissement"] = "radius"
    where_extra = ""
    params: list = [type_local, PARIS_PPM2_FLOOR, cutoff]

    if lon is not None and lat is not None:
        spatial, spatial_params = _spatial_where_clause(lon, lat, radius_m)
        where_extra = f"AND {spatial}"
        params.extend(spatial_params)
    elif code_postal:
        scope = "arrondissement"
        where_extra = "AND code_postal = ?"
        params.append(code_postal)
    else:
        return None, 0, scope

    sql = f"""
        SELECT price_per_m2
        FROM mutations
        WHERE type_local = ?
          AND price_per_m2 >= ?
          AND date_mutation >= ?
          {where_extra}
    """
    with cursor() as cur:
        rows = cur.execute(sql, params).fetchall()

    vals = [float(r[0]) for r in rows if r[0] is not None]
    if scope == "radius" and code_postal and len(vals) < MIN_SALES_PER_YEAR:
        return rolling_median_ppm2(
            lon=None,
            lat=None,
            code_postal=code_postal,
            months=months,
            radius_m=radius_m,
            type_local=type_local,
        )

    med = _median(vals)
    return (round(med) if med is not None else None, len(vals), scope)


def compute_market_position(
    price_eur: float | None,
    surface_m2: float | None,
    *,
    lon: float | None = None,
    lat: float | None = None,
    code_postal: str | None = None,
) -> MarketIndex | None:
    """Compare listing €/m² to live DVF median (last 12 months near address)."""
    if not price_eur or not surface_m2 or surface_m2 <= 0:
        return None
    if lon is None and lat is None and not code_postal:
        return None

    median, n_tx, scope = rolling_median_ppm2(
        lon=lon, lat=lat, code_postal=code_postal
    )
    if median is None:
        return None

    listing_ppm2 = price_eur / surface_m2
    vs_median_pct = ((listing_ppm2 - median) / median) * 100.0
    return MarketIndex(
        arrondissement_median_ppm2=median,
        listing_vs_median_pct=round(vs_median_pct, 1),
        scope=scope,
        n_transactions_12m=n_tx,
        data_source="dvf_live",
    )


def yoy_change_pct(trends: list[YearlyMarketTrend]) -> float | None:
    """Year-over-year change using the two most recent years with data."""
    if len(trends) < 2:
        return None
    a, b = trends[-2], trends[-1]
    if a.median_price_per_m2 <= 0:
        return None
    return round(
        ((b.median_price_per_m2 - a.median_price_per_m2) / a.median_price_per_m2)
        * 100.0,
        1,
    )
