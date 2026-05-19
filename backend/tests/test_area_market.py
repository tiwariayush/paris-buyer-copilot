"""Tests for DVF-based area market trends."""
from __future__ import annotations

import pytest

from app.models.schemas import YearlyMarketTrend
from app.services.area_market import yoy_change_pct


def test_yoy_change_pct():
    trends = [
        YearlyMarketTrend(year=2023, median_price_per_m2=10_000, transaction_count=20),
        YearlyMarketTrend(year=2024, median_price_per_m2=10_500, transaction_count=25),
    ]
    assert yoy_change_pct(trends) == 5.0


def test_yoy_change_pct_insufficient_data():
    assert yoy_change_pct([]) is None
    assert yoy_change_pct([
        YearlyMarketTrend(year=2024, median_price_per_m2=10_000, transaction_count=5),
    ]) is None


def _dvf_available() -> bool:
    try:
        from app.db import cursor
        with cursor() as cur:
            n = cur.execute("SELECT COUNT(*) FROM mutations").fetchone()[0]
        return n > 0
    except Exception:
        return False


@pytest.mark.skipif(not _dvf_available(), reason="DuckDB not available")
def test_yearly_trends_paris_arrondissement():
    from app.services.area_market import yearly_trends

    trends, scope, label = yearly_trends(
        lon=None, lat=None, code_postal="75011"
    )
    assert scope == "arrondissement"
    assert "75011" in label
    assert len(trends) >= 2
    assert all(t.median_price_per_m2 > 4000 for t in trends)
    assert all(t.transaction_count > 0 for t in trends)


@pytest.mark.skipif(not _dvf_available(), reason="DuckDB not available")
def test_rolling_median_near_republique():
    from app.services.area_market import rolling_median_ppm2

    med, n, scope = rolling_median_ppm2(
        lon=2.3636, lat=48.8676, code_postal="75011"
    )
    assert med is not None
    assert med > 5000
    assert n >= 5
    assert scope in {"radius", "arrondissement"}
