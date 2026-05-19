"""Notaires de France-style market position indicator.

Uses hardcoded quarterly median €/m² by Paris arrondissement (approximate
values based on 2024-2025 market data from Notaires de France publications).
"""
from __future__ import annotations

from ..models.schemas import MarketIndex

PARIS_MEDIAN_PPM2: dict[str, float] = {
    "75001": 13_200,
    "75002": 12_100,
    "75003": 12_500,
    "75004": 13_400,
    "75005": 12_600,
    "75006": 14_800,
    "75007": 14_200,
    "75008": 12_000,
    "75009": 10_800,
    "75010": 10_200,
    "75011": 10_000,
    "75012": 9_500,
    "75013": 9_200,
    "75014": 10_400,
    "75015": 10_100,
    "75016": 11_500,
    "75017": 10_600,
    "75018": 9_400,
    "75019": 8_500,
    "75020": 8_800,
}


def compute_market_position(
    price_eur: float | None,
    surface_m2: float | None,
    postal_code: str | None,
) -> MarketIndex | None:
    """Compare the listing's asking price/m² to the arrondissement median."""
    if not price_eur or not surface_m2 or surface_m2 <= 0 or not postal_code:
        return None
    median = PARIS_MEDIAN_PPM2.get(postal_code)
    if median is None:
        return None
    listing_ppm2 = price_eur / surface_m2
    vs_median_pct = ((listing_ppm2 - median) / median) * 100.0
    return MarketIndex(
        arrondissement_median_ppm2=median,
        listing_vs_median_pct=round(vs_median_pct, 1),
    )
