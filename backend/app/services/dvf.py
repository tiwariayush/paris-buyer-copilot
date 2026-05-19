"""DuckDB-backed DVF comparable queries.

Tiers, in order of preference:
1. Same building (id_parcelle match), last 36 months.
2. Same street (postal code + voie name), last 24 months, surface within ±30%.
3. Same IRIS or commune, last 18 months, surface ±30%, same type_local.

Spatial fallback (within 500m radius) is also exposed for cases where parcel
and IRIS are unavailable.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..db import cursor
from ..models.schemas import Comp


def _row_to_comp(r: tuple[Any, ...], tier: str) -> Comp:
    return Comp(
        id_mutation=r[0],
        date_mutation=r[1],
        valeur_fonciere=r[2],
        surface_reelle_bati=r[3],
        nombre_pieces_principales=r[4],
        type_local=r[5],
        adresse=r[6],
        code_postal=r[7],
        id_parcelle=r[8],
        longitude=r[9],
        latitude=r[10],
        price_per_m2=r[11],
        tier=tier,  # type: ignore[arg-type]
    )


_BASE_COLS = """
    id_mutation,
    date_mutation,
    valeur_fonciere,
    surface_reelle_bati,
    nombre_pieces_principales,
    type_local,
    adresse,
    code_postal,
    id_parcelle,
    longitude,
    latitude,
    price_per_m2
"""

# Paris: parking spots / cellars / partial shares of co-ownership routinely
# show up below 4 000 €/m² and would otherwise drag the median down.
PARIS_PPM2_FLOOR = 4000


def building_comps(
    id_parcelle: str,
    *,
    months: int = 36,
    type_local: str = "Appartement",
    limit: int = 50,
) -> list[Comp]:
    if not id_parcelle:
        return []
    cutoff = date.today() - timedelta(days=months * 30)
    sql = f"""
        SELECT {_BASE_COLS}
        FROM mutations
        WHERE id_parcelle = ?
          AND date_mutation >= ?
          AND type_local = ?
          AND price_per_m2 >= ?
        ORDER BY date_mutation DESC
        LIMIT ?;
    """
    with cursor() as cur:
        rows = cur.execute(
            sql, [id_parcelle, cutoff, type_local, PARIS_PPM2_FLOOR, limit]
        ).fetchall()
    return [_row_to_comp(r, "building") for r in rows]


def street_comps(
    voie: str,
    code_postal: str,
    surface_target: float,
    *,
    months: int = 24,
    type_local: str = "Appartement",
    surface_tolerance: float = 0.3,
    limit: int = 50,
) -> list[Comp]:
    if not voie or not code_postal:
        return []
    cutoff = date.today() - timedelta(days=months * 30)
    smin = surface_target * (1 - surface_tolerance)
    smax = surface_target * (1 + surface_tolerance)
    sql = f"""
        SELECT {_BASE_COLS}
        FROM mutations
        WHERE code_postal = ?
          AND adresse_nom_voie = ?
          AND date_mutation >= ?
          AND type_local = ?
          AND surface_reelle_bati BETWEEN ? AND ?
          AND price_per_m2 >= ?
        ORDER BY date_mutation DESC
        LIMIT ?;
    """
    with cursor() as cur:
        rows = cur.execute(
            sql,
            [
                code_postal, voie.upper(), cutoff, type_local,
                smin, smax, PARIS_PPM2_FLOOR, limit,
            ],
        ).fetchall()
    return [_row_to_comp(r, "street") for r in rows]


def radius_comps(
    lon: float,
    lat: float,
    surface_target: float,
    *,
    radius_m: int = 500,
    months: int = 18,
    type_local: str = "Appartement",
    surface_tolerance: float = 0.3,
    limit: int = 60,
) -> list[Comp]:
    """IRIS substitute: spatial radius via DuckDB spatial extension."""
    if lon is None or lat is None:
        return []
    cutoff = date.today() - timedelta(days=months * 30)
    smin = surface_target * (1 - surface_tolerance)
    smax = surface_target * (1 + surface_tolerance)
    # Approx 1 degree latitude = 111_000m; longitude scale by cos(lat).
    sql = f"""
        WITH base AS (
            SELECT {_BASE_COLS},
                   ST_Distance_Sphere(
                       ST_Point(longitude, latitude),
                       ST_Point(?, ?)
                   ) AS distance_m
            FROM mutations
            WHERE longitude IS NOT NULL AND latitude IS NOT NULL
              AND date_mutation >= ?
              AND type_local = ?
              AND surface_reelle_bati BETWEEN ? AND ?
              AND price_per_m2 >= {PARIS_PPM2_FLOOR}
              AND ABS(latitude - ?) < ?
              AND ABS(longitude - ?) < ?
        )
        SELECT * FROM base
        WHERE distance_m <= ?
        ORDER BY distance_m ASC
        LIMIT ?;
    """
    deg_lat = radius_m / 111_000
    deg_lon = radius_m / (111_000 * max(0.1, abs(_cos_deg(lat))))
    with cursor() as cur:
        rows = cur.execute(
            sql,
            [
                lon, lat,
                cutoff, type_local,
                smin, smax,
                lat, deg_lat,
                lon, deg_lon,
                radius_m, limit,
            ],
        ).fetchall()
    out: list[Comp] = []
    for r in rows:
        comp = _row_to_comp(r[:-1], "iris")
        comp.distance_m = r[-1]
        out.append(comp)
    return out


def _cos_deg(deg: float) -> float:
    import math
    return math.cos(math.radians(deg))


def building_history(id_parcelle: str) -> list[Comp]:
    """ALL transactions for a building (any type/surface), ordered by date desc.

    Unlike building_comps() which filters by type_local and price floor,
    this returns the full transaction record as a trust signal for the user.
    """
    if not id_parcelle:
        return []
    sql = f"""
        SELECT {_BASE_COLS}
        FROM mutations
        WHERE id_parcelle = ?
          AND surface_reelle_bati IS NOT NULL
          AND price_per_m2 IS NOT NULL
        ORDER BY date_mutation DESC
        LIMIT 100;
    """
    with cursor() as cur:
        rows = cur.execute(sql, [id_parcelle]).fetchall()
    return [_row_to_comp(r, "building") for r in rows]


def find_comps(
    *,
    id_parcelle: str | None,
    voie: str | None,
    code_postal: str | None,
    lon: float | None,
    lat: float | None,
    surface: float | None,
    type_local: str = "Appartement",
) -> tuple[list[Comp], str]:
    """Run the tiered cascade. Returns (comps, base_tier)."""
    surface = surface or 50.0  # minimal default to avoid div0
    # Tier 1: building
    if id_parcelle:
        building = building_comps(id_parcelle, type_local=type_local)
        if len(building) >= 3:
            return building, "building"
    else:
        building = []
    # Tier 2: street
    street: list[Comp] = []
    if voie and code_postal:
        street = street_comps(voie, code_postal, surface, type_local=type_local)
    if len(building) + len(street) >= 5 and street:
        return building + street, "street"
    # Tier 3: radius / IRIS
    radius: list[Comp] = []
    if lon is not None and lat is not None:
        radius = radius_comps(lon, lat, surface, type_local=type_local)
    combined = building + street + radius
    if combined:
        return combined, "iris" if not building else ("building" if len(building) >= 3 else "iris")
    return [], "none"


def find_display_comps(
    *,
    id_parcelle: str | None,
    voie: str | None,
    code_postal: str | None,
    lon: float | None,
    lat: float | None,
    surface: float | None,
    type_local: str = "Appartement",
    max_results: int = 150,
) -> list[Comp]:
    """Broader merge of building + street + radius comps for the UI table.

    Unlike find_comps(), does not stop at the first tier — surfaces up to
    ~7 years of DVF history (subject to what is ingested in DuckDB).
    """
    surface = surface or 50.0
    seen: set[str] = set()
    merged: list[Comp] = []

    def _add(batch: list[Comp]) -> None:
        for c in batch:
            if c.id_mutation in seen:
                continue
            seen.add(c.id_mutation)
            merged.append(c)

    if id_parcelle:
        _add(
            building_comps(
                id_parcelle, months=84, limit=100, type_local=type_local
            )
        )
    if voie and code_postal:
        _add(
            street_comps(
                voie,
                code_postal,
                surface,
                months=60,
                limit=100,
                type_local=type_local,
            )
        )
    if lon is not None and lat is not None:
        _add(
            radius_comps(
                lon,
                lat,
                surface,
                months=60,
                limit=120,
                radius_m=750,
                type_local=type_local,
            )
        )

    merged.sort(key=lambda c: c.date_mutation, reverse=True)
    return merged[:max_results]


def stats() -> dict[str, Any]:
    """Quick health stats (used by /health)."""
    with cursor() as cur:
        n = cur.execute("SELECT COUNT(*) FROM mutations;").fetchone()[0]
        last = cur.execute(
            "SELECT MAX(date_mutation) FROM mutations;"
        ).fetchone()[0]
    return {"mutations": n, "latest": str(last) if last else None}
