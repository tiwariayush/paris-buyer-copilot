"""End-to-end /analyze test, mocking out the network calls.

This proves the full pipeline composes correctly:
listing parser -> geocoder -> dvf -> valuation -> ai (fallback) -> JSON.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import GeoLocation, DPEReport
from app.services import dpe, geocoder, listing_parser, neighborhood
from app.models.schemas import Neighborhood

DB = settings().duckdb_path

pytestmark = pytest.mark.skipif(
    not DB.exists() or os.getenv("SKIP_DVF") == "1",
    reason="DuckDB not yet ingested",
)


HTML = """
<!doctype html><html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "RealEstateListing",
  "name": "Appart 3p 65m² République",
  "description": "Bel appartement, 4e étage, ascenseur. DPE D.",
  "offers": {"price": 720000, "priceCurrency": "EUR"},
  "address": {"streetAddress": "5 rue du Faubourg du Temple", "postalCode": "75011", "addressLocality": "Paris"},
  "floorSize": {"value": 65},
  "numberOfRooms": 3
}
</script></head><body></body></html>
"""


@pytest.fixture
def client(monkeypatch):
    async def fake_fetch(url: str) -> str:
        return HTML

    async def fake_geocode(address, postcode=None, **kw):
        return GeoLocation(
            lat=48.8676,
            lon=2.3636,
            address_normalized="5 rue du Faubourg du Temple, 75011 Paris",
            score=0.95,
            id_parcelle=None,
            code_iris="751114001",
            nom_iris="République",
            code_commune="75111",
            code_postal="75011",
        )

    async def fake_dpe(*a, **kw):
        return DPEReport(dpe_class="D", surface_m2=65.0, year_certified=2023)

    async def fake_nbh(*a, **kw):
        return Neighborhood(iris_code="751114001", iris_name="République")

    monkeypatch.setattr(listing_parser, "fetch", fake_fetch)
    monkeypatch.setattr(geocoder, "geocode", fake_geocode)
    monkeypatch.setattr(dpe, "lookup", fake_dpe)
    monkeypatch.setattr(neighborhood, "enrich", fake_nbh)
    return TestClient(app)


def test_analyze_end_to_end(client):
    r = client.post(
        "/analyze",
        json={"content": "https://www.bienici.com/annonce/test"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["listing"]["price_eur"] == 720_000
    assert body["listing"]["surface_m2"] == 65
    assert body["valuation"]["n_comps"] >= 0
    # We have DVF data in République area, so we expect some comps.
    assert body["valuation"]["base_tier"] in {"iris", "street", "building"}
    assert body["negotiation"]["verdict"]
    assert len(body["negotiation"]["levers"]) >= 1
    assert body["negotiation"]["opening_message"]
