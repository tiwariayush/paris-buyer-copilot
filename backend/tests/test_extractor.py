"""Smoke tests for the LLM-paste extractor (regex fallback path)."""
from __future__ import annotations

import pytest

from app.services import extractor


SELOGER_PASTE = """\
Appartement à vendre - Paris 11ème (75011)
3 pièces, 65 m²
850 000 €
13 077 €/m²

Description
Bel appartement traversant au 4ème étage avec ascenseur, situé dans une rue
calme du quartier République. Cuisine ouverte, parquet, double exposition.
Charges 220 €/mois.

DPE: D · GES: B
Adresse: 5 rue du Faubourg du Temple, 75011 Paris
"""


@pytest.mark.asyncio
async def test_extractor_regex_fallback(monkeypatch):
    # Force the regex path by clearing the API key in settings.
    from app.config import settings
    monkeypatch.setattr(settings(), "openai_api_key", None)

    listing = await extractor.extract(SELOGER_PASTE)
    assert listing.price_eur == 850_000
    assert listing.surface_m2 == 65
    assert listing.rooms == 3
    assert listing.postal_code == "75011"
    assert listing.dpe_class == "D"
    assert listing.floor == 4
    assert listing.has_elevator is True


@pytest.mark.asyncio
async def test_extractor_rejects_rental(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings(), "openai_api_key", None)

    rental = (
        "Studio à louer Paris 15e, 22 m², 1 100 €/mois charges comprises. "
        "DPE: E. Disponible immédiatement."
    )
    with pytest.raises(extractor.ExtractionError, match="location"):
        await extractor.extract(rental)


@pytest.mark.asyncio
async def test_extractor_rejects_short_input():
    with pytest.raises(extractor.ExtractionError, match="trop court"):
        await extractor.extract("hi")


@pytest.mark.asyncio
async def test_extractor_rejects_no_price(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings(), "openai_api_key", None)
    text = "Joli T2 65m² Paris 11e étage 4 avec ascenseur, DPE C. Adresse au 5 rue du Faubourg du Temple 75011."
    with pytest.raises(extractor.ExtractionError, match="prix"):
        await extractor.extract(text)
