"""INSEE Filosofi-style household income reference data.

Hardcoded median household income by Paris arrondissement, based on
INSEE Filosofi 2021 publication (arrondissement-level aggregation).
Values are approximate annual median disposable income per household in EUR.
"""
from __future__ import annotations

PARIS_MEDIAN_INCOME: dict[str, float] = {
    "75001": 38_500,
    "75002": 36_200,
    "75003": 38_000,
    "75004": 39_200,
    "75005": 37_800,
    "75006": 46_500,
    "75007": 50_200,
    "75008": 44_800,
    "75009": 33_500,
    "75010": 29_800,
    "75011": 30_500,
    "75012": 32_200,
    "75013": 27_500,
    "75014": 33_800,
    "75015": 35_200,
    "75016": 48_000,
    "75017": 36_500,
    "75018": 26_200,
    "75019": 24_500,
    "75020": 26_800,
}


def get_median_income(postal_code: str | None) -> float | None:
    """Return the arrondissement-level median household income for a postcode."""
    if not postal_code:
        return None
    return PARIS_MEDIAN_INCOME.get(postal_code)
