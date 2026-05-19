"""Tests for vue / luminosité detection and valuation impact."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.schemas import Comp, Listing, PremiumFeatures
from app.services.premium_features import detect_from_text, merge_premium
from app.services.valuation import value_listing


def _listing(**kwargs) -> Listing:
    base = {
        "source_url": "https://example.com",
        "portal": "test",
        "price_eur": 900_000,
        "surface_m2": 65,
    }
    return Listing(**(base | kwargs))


def _comp(ppm2: float = 11_000) -> Comp:
    d = date.today() - timedelta(days=60)
    return Comp(
        id_mutation="M1",
        date_mutation=d,
        valeur_fonciere=ppm2 * 65,
        surface_reelle_bati=65,
        nombre_pieces_principales=3,
        type_local="Appartement",
        adresse="1 rue test",
        code_postal="75007",
        id_parcelle="X",
        longitude=2.3,
        latitude=48.86,
        price_per_m2=ppm2,
        tier="building",
    )


def test_detect_eiffel_view_and_luminous():
    text = (
        "Superbe appartement avec vue Tour Eiffel dégagée. "
        "Très lumineux, double exposition est-ouest."
    )
    view, light, highlights, sources = detect_from_text(text)
    assert view == "landmark"
    assert light == "exceptional"
    assert "Vue Tour Eiffel" in highlights
    assert "description" in sources


def test_proche_eiffel_not_landmark():
    text = "Quartier calme, proche de la Tour Eiffel et des commerces."
    view, _, _, _ = detect_from_text(text)
    assert view == "none"


def test_merge_from_description_only():
    listing = _listing(
        description="Bel appartement lumineux avec vue panoramique sur Paris.",
    )
    premium = merge_premium(listing)
    assert premium is not None
    assert premium.view_tier == "panoramic"
    assert premium.light_tier == "bright"


def test_landmark_view_raises_fair_value():
    comps = [_comp(10_000) for _ in range(6)]
    base = _listing()
    premium = PremiumFeatures(
        view_tier="landmark",
        light_tier="bright",
        highlights_fr=["Vue Tour Eiffel"],
        sources=["description"],
    )
    val_plain = value_listing(base, comps, "building")
    val_premium = value_listing(base, comps, "building", premium=premium)
    assert val_plain.fair_value_eur is not None
    assert val_premium.fair_value_eur is not None
    assert val_premium.fair_value_eur > val_plain.fair_value_eur
    assert "view_landmark" in val_premium.adjustments
    assert "light_bright" in val_premium.adjustments
