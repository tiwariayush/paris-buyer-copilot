"""Golden listing regression suite.

Hand-curated Paris apartment archetypes covering diverse arrondissements,
surfaces, DPE classes, and floor configurations. Each has an expected
price/m² range based on market knowledge. The test checks that our
valuation falls within the expected band.

These are synthetic listings (not real URLs) designed to exercise the
valuation engine's hedonic adjustments and comp selection logic.

Run: uv run pytest tests/test_golden_listings.py -v
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from app.models.schemas import Comp, Listing
from app.services.valuation import value_listing


def _dvf_available() -> bool:
    try:
        from app.db import cursor
        with cursor() as cur:
            n = cur.execute("SELECT COUNT(*) FROM mutations").fetchone()[0]
        return n > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _dvf_available(),
    reason="DuckDB file not available; skip golden listing tests",
)


def _make_listing(**kwargs) -> Listing:
    defaults = {
        "source_url": "https://golden-test.local/",
        "portal": "golden_test",
    }
    return Listing(**(defaults | kwargs))


def _get_real_comps(
    code_postal: str,
    surface: float,
    lon: float,
    lat: float,
) -> tuple[list[Comp], str]:
    """Pull real comps from DVF for the golden listing."""
    from app.services.dvf import find_comps
    return find_comps(
        id_parcelle=None,
        voie=None,
        code_postal=code_postal,
        lon=lon,
        lat=lat,
        surface=surface,
        type_local="Appartement",
    )


# Each golden case: (name, listing_kwargs, approx_lon, approx_lat, expected_ppm2_range)
GOLDEN_CASES = [
    # 1. Studio Marais (3e) — small, premium area, DPE D, no elevator
    (
        "Studio Marais 3e",
        dict(price_eur=280_000, surface_m2=22, rooms=1, postal_code="75003",
             address_raw="Marais, 75003", dpe_class="D", floor=4, has_elevator=False),
        2.3600, 48.8630,
        (9_000, 15_000),
    ),
    # 2. 2P Bastille (11e) — average, DPE E, with elevator
    (
        "2P Bastille 11e",
        dict(price_eur=420_000, surface_m2=42, rooms=2, postal_code="75011",
             address_raw="Bastille, 75011", dpe_class="E", floor=5, has_elevator=True),
        2.3700, 48.8530,
        (8_500, 13_000),
    ),
    # 3. 3P Montmartre (18e) — trendy but mixed area
    (
        "3P Montmartre 18e",
        dict(price_eur=550_000, surface_m2=60, rooms=3, postal_code="75018",
             address_raw="Montmartre, 75018", dpe_class="D", floor=3, has_elevator=True),
        2.3430, 48.8870,
        (7_500, 12_500),
    ),
    # 4. 4P Passy (16e) — bourgeois, DPE C, top floor
    (
        "4P Passy 16e",
        dict(price_eur=1_200_000, surface_m2=95, rooms=4, postal_code="75016",
             address_raw="Passy, 75016", dpe_class="C", floor=6, has_elevator=True),
        2.2750, 48.8580,
        (10_000, 16_000),
    ),
    # 5. 2P Belleville (20e) — popular, DPE F, walk-up
    (
        "2P Belleville 20e",
        dict(price_eur=250_000, surface_m2=35, rooms=2, postal_code="75020",
             address_raw="Belleville, 75020", dpe_class="F", floor=5, has_elevator=False),
        2.3880, 48.8720,
        (6_000, 11_000),
    ),
    # 6. Large family 5P (15e) — residential, DPE D
    (
        "5P Convention 15e",
        dict(price_eur=950_000, surface_m2=110, rooms=5, postal_code="75015",
             address_raw="Convention, 75015", dpe_class="D", floor=4, has_elevator=True),
        2.2950, 48.8400,
        (8_000, 13_000),
    ),
    # 7. Studio Quartier Latin (5e) — student area, premium
    (
        "Studio Quartier Latin 5e",
        dict(price_eur=220_000, surface_m2=18, rooms=1, postal_code="75005",
             address_raw="Quartier Latin, 75005", dpe_class="E", floor=6, has_elevator=False),
        2.3470, 48.8490,
        (9_500, 16_000),
    ),
    # 8. 3P Oberkampf (11e) — hipster, DPE C, renovated
    (
        "3P Oberkampf 11e",
        dict(price_eur=650_000, surface_m2=55, rooms=3, postal_code="75011",
             address_raw="Oberkampf, 75011", dpe_class="C", floor=2, has_elevator=True),
        2.3790, 48.8650,
        (8_500, 14_000),
    ),
    # 9. 2P Nation (12e) — solid middle class
    (
        "2P Nation 12e",
        dict(price_eur=380_000, surface_m2=45, rooms=2, postal_code="75012",
             address_raw="Nation, 75012", dpe_class="D", floor=3, has_elevator=True),
        2.3960, 48.8480,
        (7_000, 12_000),
    ),
    # 10. 4P Saint-Germain (6e) — ultra-premium
    (
        "4P Saint-Germain 6e",
        dict(price_eur=1_800_000, surface_m2=100, rooms=4, postal_code="75006",
             address_raw="Saint-Germain-des-Prés, 75006", dpe_class="D", floor=4, has_elevator=True),
        2.3330, 48.8540,
        (12_000, 20_000),
    ),
    # 11. Studio Goutte d'Or (18e) — affordable, DPE G
    (
        "Studio Goutte d'Or 18e",
        dict(price_eur=120_000, surface_m2=15, rooms=1, postal_code="75018",
             address_raw="Goutte d'Or, 75018", dpe_class="G", floor=3, has_elevator=False),
        2.3500, 48.8850,
        (5_500, 10_500),
    ),
    # 12. 3P Batignolles (17e) — gentrifying
    (
        "3P Batignolles 17e",
        dict(price_eur=700_000, surface_m2=65, rooms=3, postal_code="75017",
             address_raw="Batignolles, 75017", dpe_class="D", floor=5, has_elevator=True),
        2.3180, 48.8830,
        (8_500, 14_000),
    ),
    # 13. 2P Alésia (14e) — quiet residential
    (
        "2P Alésia 14e",
        dict(price_eur=400_000, surface_m2=40, rooms=2, postal_code="75014",
             address_raw="Alésia, 75014", dpe_class="E", floor=1, has_elevator=True),
        2.3270, 48.8280,
        (7_500, 12_500),
    ),
    # 14. 4P Opéra/Grands Boulevards (9e) — central, Haussmann
    (
        "4P Grands Boulevards 9e",
        dict(price_eur=1_100_000, surface_m2=85, rooms=4, postal_code="75009",
             address_raw="Grands Boulevards, 75009", dpe_class="D", floor=5, has_elevator=True),
        2.3430, 48.8740,
        (9_000, 15_000),
    ),
    # 15. 2P Buttes-Chaumont (19e) — park proximity premium
    (
        "2P Buttes-Chaumont 19e",
        dict(price_eur=350_000, surface_m2=38, rooms=2, postal_code="75019",
             address_raw="Buttes-Chaumont, 75019", dpe_class="D", floor=4, has_elevator=True),
        2.3810, 48.8810,
        (7_000, 12_000),
    ),
]


@pytest.mark.parametrize(
    "name,listing_kwargs,lon,lat,expected_ppm2_range",
    GOLDEN_CASES,
    ids=[c[0] for c in GOLDEN_CASES],
)
def test_golden_listing(
    name: str,
    listing_kwargs: dict,
    lon: float,
    lat: float,
    expected_ppm2_range: tuple[int, int],
):
    listing = _make_listing(**listing_kwargs)
    comps, tier = _get_real_comps(
        listing.postal_code,
        listing.surface_m2,
        lon,
        lat,
    )

    val = value_listing(listing, comps, tier)

    assert val.n_comps > 0, f"{name}: no comps found"
    assert val.fair_value_eur is not None, f"{name}: no fair value"
    assert val.price_per_m2_estimate is not None, f"{name}: no price/m² estimate"

    ppm2_low, ppm2_high = expected_ppm2_range
    assert ppm2_low <= val.price_per_m2_estimate <= ppm2_high, (
        f"{name}: estimated {val.price_per_m2_estimate:,.0f} €/m² "
        f"outside expected range [{ppm2_low:,}–{ppm2_high:,}] €/m². "
        f"tier={tier}, n_comps={val.n_comps}, confidence={val.confidence}"
    )

    # Band should be reasonable (not wider than 80% of fair value)
    if val.fair_value_low_eur and val.fair_value_high_eur:
        band_width = val.fair_value_high_eur - val.fair_value_low_eur
        band_pct = band_width / val.fair_value_eur if val.fair_value_eur else 999
        assert band_pct < 0.80, (
            f"{name}: band too wide ({band_pct:.0%}), "
            f"[{val.fair_value_low_eur:,.0f}–{val.fair_value_high_eur:,.0f}]"
        )
