"""Smoke tests for valuation logic."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.schemas import Comp, Listing
from app.services.valuation import value_listing


def make_listing(price=900_000, surface=65.0, dpe=None, floor=None, elev=None):
    return Listing(
        source_url="https://example.com",
        portal="test",
        price_eur=price,
        surface_m2=surface,
        rooms=3,
        dpe_class=dpe,
        floor=floor,
        has_elevator=elev,
    )


def make_comp(ppm2: float, surface: float = 65.0, days_ago: int = 90):
    d = date.today() - timedelta(days=days_ago)
    return Comp(
        id_mutation=f"M{ppm2}",
        date_mutation=d,
        valeur_fonciere=ppm2 * surface,
        surface_reelle_bati=surface,
        nombre_pieces_principales=3,
        type_local="Appartement",
        adresse="1 rue test",
        code_postal="75011",
        id_parcelle="751110000A0001",
        longitude=2.37,
        latitude=48.86,
        price_per_m2=ppm2,
        tier="building",
    )


def test_value_with_building_comps():
    listing = make_listing()
    comps = [make_comp(p) for p in [10_500, 11_000, 10_800, 10_900, 11_200]]
    val = value_listing(listing, comps, "building")
    assert val.fair_value_eur is not None
    assert 660_000 < val.fair_value_eur < 760_000
    assert val.n_comps == 5
    assert val.confidence in {"medium", "high"}
    assert val.base_tier == "building"


def test_dpe_g_drops_value():
    listing_a = make_listing(dpe="C")
    listing_g = make_listing(dpe="G")
    comps = [make_comp(p) for p in [11_000, 10_800, 11_200, 10_900]]
    val_a = value_listing(listing_a, comps, "building")
    val_g = value_listing(listing_g, comps, "building")
    assert val_g.fair_value_eur is not None
    assert val_a.fair_value_eur is not None
    assert val_g.fair_value_eur < val_a.fair_value_eur * 0.93


def test_no_comps_returns_low_confidence():
    listing = make_listing()
    val = value_listing(listing, [], "none")
    assert val.confidence == "low"
    assert val.fair_value_eur is None
    assert val.base_tier == "none"
