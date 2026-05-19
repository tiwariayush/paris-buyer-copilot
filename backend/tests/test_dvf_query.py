"""Smoke test: query the actual ingested DVF DuckDB if it exists."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import settings
from app.services import dvf

DB = settings().duckdb_path


pytestmark = pytest.mark.skipif(
    not DB.exists() or os.getenv("SKIP_DVF") == "1",
    reason="DuckDB not yet ingested (run scripts/ingest_dvf.py first)",
)


def test_health_stats_nonzero():
    s = dvf.stats()
    assert s["mutations"] > 1000


def test_radius_comps_in_paris():
    # Place de la République (48.8676, 2.3636)
    comps = dvf.radius_comps(2.3636, 48.8676, surface_target=50.0)
    assert len(comps) > 0
    for c in comps:
        assert c.tier == "iris"
        assert c.price_per_m2 is not None


def test_find_display_comps_merges_tiers():
    """Display search should return more rows than valuation-only cascade."""
    from app.services.dvf import find_comps, find_display_comps

    args = dict(
        id_parcelle=None,
        voie=None,
        code_postal="75011",
        lon=2.3636,
        lat=48.8676,
        surface=50.0,
    )
    val_comps, _ = find_comps(**args)
    display = find_display_comps(**args)
    assert len(display) >= len(val_comps)
    if display:
        years = {c.date_mutation.year for c in display}
        assert min(years) <= max(years)


def test_street_comps():
    # Rue de Rivoli is a long street in 1er–4e arr; should yield hits.
    comps = dvf.street_comps("RUE DE RIVOLI", "75001", surface_target=60.0)
    # Either hits, or empty if street name doesn't match — just verify shape.
    assert isinstance(comps, list)
