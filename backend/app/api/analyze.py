"""POST /analyze — paste a listing URL, get fair value + comps + negotiation."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from ..models.schemas import AnalyzeRequest, AnalyzeResponse
from ..services import ai, dpe, dvf, geocoder, listing_parser, neighborhood, valuation

router = APIRouter()


def _voie_from_address(addr: str | None) -> str | None:
    """Best-effort extraction of street name as DVF stores it (uppercase, no number).

    DVF's adresse_nom_voie is the street name uppercased (e.g. 'RUE DE RIVOLI'),
    without the leading number/suffix and without the type prefix in some cases.
    """
    if not addr:
        return None
    s = addr.upper()
    # Strip leading number(s) and bis/ter
    s = re.sub(r"^\s*\d+[A-Z]?\s*(BIS|TER|QUATER)?\s*[,]?\s*", "", s)
    # Trim postcode + city tail if present
    s = re.split(r",\s*\d{5}", s)[0]
    s = s.strip().strip(",").strip()
    return s or None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    url = str(req.url)
    warnings: list[str] = []

    try:
        listing = await listing_parser.parse_url(url)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse listing URL: {e}",
        ) from e

    if not listing.address_raw:
        warnings.append(
            "No address found in the listing markup; comps may fall back to a wide radius."
        )

    location = None
    if listing.address_raw:
        try:
            location = await geocoder.geocode(
                listing.address_raw, listing.postal_code
            )
        except Exception as e:
            warnings.append(f"Geocoding failed: {e}")

    voie = _voie_from_address(listing.address_raw)
    code_postal = (
        listing.postal_code
        or (location.code_postal if location else None)
    )

    type_local = "Appartement"  # Paris MVP focuses on apartments
    comps, base_tier = dvf.find_comps(
        id_parcelle=location.id_parcelle if location else None,
        voie=voie,
        code_postal=code_postal,
        lon=location.lon if location else None,
        lat=location.lat if location else None,
        surface=listing.surface_m2,
        type_local=type_local,
    )

    val = valuation.value_listing(listing, comps, base_tier)

    delta_eur = None
    delta_pct = None
    if listing.price_eur and val.fair_value_eur:
        delta_eur = listing.price_eur - val.fair_value_eur
        delta_pct = (delta_eur / val.fair_value_eur) * 100.0

    dpe_report = None
    try:
        dpe_report = await dpe.lookup(
            listing.address_raw, listing.postal_code, surface=listing.surface_m2
        )
    except Exception as e:
        warnings.append(f"DPE lookup failed: {e}")
    if dpe_report and dpe_report.dpe_class and not listing.dpe_class:
        listing.dpe_class = dpe_report.dpe_class
        # re-value with the DPE adjustment now known
        val = valuation.value_listing(listing, comps, base_tier)
        if listing.price_eur and val.fair_value_eur:
            delta_eur = listing.price_eur - val.fair_value_eur
            delta_pct = (delta_eur / val.fair_value_eur) * 100.0

    nbh = None
    if location:
        try:
            nbh = await neighborhood.enrich(
                location.lat,
                location.lon,
                location.code_iris,
                location.nom_iris,
                postcode=listing.postal_code or location.code_postal,
            )
        except Exception as e:
            warnings.append(f"Neighborhood lookup failed: {e}")

    negotiation = await ai.negotiate(
        listing, val, comps, delta_pct, delta_eur, dpe_report
    )

    return AnalyzeResponse(
        listing=listing,
        location=location,
        valuation=val,
        comps=comps[:30],
        dpe=dpe_report,
        neighborhood=nbh,
        negotiation=negotiation,
        delta_pct=delta_pct,
        delta_eur=delta_eur,
        warnings=warnings,
    )
