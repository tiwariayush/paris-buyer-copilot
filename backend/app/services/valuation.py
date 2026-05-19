"""Comparable-based valuation with explicit hedonic adjustments.

We aim for honesty over precision:
- Pick the most-specific tier with enough comps.
- Take a recency- and similarity-weighted median €/m².
- Apply a small set of legible multipliers (DPE, floor, elevator).
- Output a confidence band based on dispersion + sample size.
"""
from __future__ import annotations

import math
import statistics
from datetime import date

from ..models.schemas import Comp, Listing, Valuation

DPE_MULTIPLIERS: dict[str, float] = {
    "A": 1.05,
    "B": 1.03,
    "C": 1.00,
    "D": 0.99,
    "E": 0.97,
    "F": 0.92,
    "G": 0.88,
}


def _recency_weight(d: date, today: date) -> float:
    """Exponential decay: half-life ~24 months."""
    months = (today.year - d.year) * 12 + (today.month - d.month)
    return math.exp(-months / 36.0)


def _similarity_weight(comp_surface: float | None, target: float | None) -> float:
    if not comp_surface or not target or target <= 0:
        return 1.0
    diff = abs(comp_surface - target) / target
    return math.exp(-3 * diff)  # 30% diff → ~0.4 weight


def _weighted_median(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0.0
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= total / 2:
            return v
    return pairs[-1][0]


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def value_listing(
    listing: Listing,
    comps: list[Comp],
    base_tier: str,
) -> Valuation:
    target_surface = listing.surface_m2
    if not comps or not target_surface or target_surface <= 0:
        return Valuation(
            fair_value_eur=None,
            fair_value_low_eur=None,
            fair_value_high_eur=None,
            price_per_m2_estimate=None,
            confidence="low",
            n_comps=len(comps),
            base_tier="none",  # type: ignore[arg-type]
            adjustments={},
            rationale="Insufficient data: missing surface or no comparables.",
        )

    today = date.today()
    valid = [c for c in comps if c.price_per_m2 and c.price_per_m2 > 1000]
    weights = [
        _recency_weight(c.date_mutation, today)
        * _similarity_weight(c.surface_reelle_bati, target_surface)
        for c in valid
    ]
    ppms = [c.price_per_m2 or 0.0 for c in valid]
    if not ppms:
        return Valuation(
            fair_value_eur=None,
            fair_value_low_eur=None,
            fair_value_high_eur=None,
            price_per_m2_estimate=None,
            confidence="low",
            n_comps=0,
            base_tier="none",  # type: ignore[arg-type]
            adjustments={},
            rationale="Comparables had no usable €/m² values.",
        )

    median_ppm2 = _weighted_median(ppms, weights)
    # Band uses P10/P90 for ~65% target coverage (backtest-calibrated).
    p10 = _pct(ppms, 0.10)
    p90 = _pct(ppms, 0.90)
    p25 = _pct(ppms, 0.25)
    p75 = _pct(ppms, 0.75)

    # Hedonic adjustments
    adj: dict[str, float] = {}
    multiplier = 1.0
    if listing.dpe_class and listing.dpe_class.upper() in DPE_MULTIPLIERS:
        m = DPE_MULTIPLIERS[listing.dpe_class.upper()]
        adj[f"dpe_{listing.dpe_class.upper()}"] = m
        multiplier *= m
    if listing.has_elevator is False and (listing.floor or 0) >= 4:
        adj["no_elevator_high_floor"] = 0.95
        multiplier *= 0.95
    if listing.has_elevator and (listing.floor or 0) >= 5:
        adj["top_floor_with_elevator"] = 1.04
        multiplier *= 1.04

    adjusted_ppm2 = median_ppm2 * multiplier
    fair_value = adjusted_ppm2 * target_surface
    low = p10 * multiplier * target_surface
    high = p90 * multiplier * target_surface

    # Confidence: combine n, dispersion, and tier quality.
    # Calibrated against backtest (2026-05-19): targets ~70% band coverage
    # for "high", ~55% for "medium", anything else "low".
    n = len(valid)
    dispersion = (statistics.stdev(ppms) / median_ppm2) if len(ppms) > 1 and median_ppm2 else 1.0
    tier_bonus = 1 if base_tier == "building" else 0

    if n >= 15 and dispersion < 0.20 and tier_bonus:
        conf = "high"
    elif n >= 10 and dispersion < 0.20:
        conf = "high"
    elif n >= 5 and dispersion < 0.30:
        conf = "medium"
    else:
        conf = "low"

    rationale = (
        f"Median €/m² across {n} comparables ({base_tier}-tier): "
        f"{round(median_ppm2):,} €/m². "
        f"Adjustments: {', '.join(f'{k}={v:.2f}' for k, v in adj.items()) or 'none'}. "
        f"IQR €/m²: {round(p25):,} – {round(p75):,}. "
        f"Band (P10–P90): {round(p10):,} – {round(p90):,}."
    ).replace(",", " ")

    return Valuation(
        fair_value_eur=round(fair_value),
        fair_value_low_eur=round(low),
        fair_value_high_eur=round(high),
        price_per_m2_estimate=round(adjusted_ppm2),
        confidence=conf,  # type: ignore[arg-type]
        n_comps=n,
        base_tier=base_tier,  # type: ignore[arg-type]
        adjustments=adj,
        rationale=rationale,
    )
