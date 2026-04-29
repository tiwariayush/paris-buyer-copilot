"""POST /analyze — paste a listing URL **or** the listing's text/HTML."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from ..models.schemas import AnalyzeRequest, AnalyzeResponse, Listing
from ..services import (
    ai,
    dpe,
    dvf,
    extractor,
    geocoder,
    listing_parser,
    neighborhood,
    valuation,
)

router = APIRouter()


_URL_RE = re.compile(r"^\s*https?://[^\s]+\s*$", re.IGNORECASE)
_PORTAL_BLOCK_HINTS = (
    "403", "Forbidden", "DataDome", "CloudFront", "captcha",
    "blocked", "Access Denied", "/jail",
)


def _voie_from_address(addr: str | None) -> str | None:
    """Best-effort extraction of street name as DVF stores it (uppercase)."""
    if not addr:
        return None
    s = addr.upper()
    s = re.sub(r"^\s*\d+[A-Z]?\s*(BIS|TER|QUATER)?\s*[,]?\s*", "", s)
    s = re.split(r",\s*\d{5}", s)[0]
    return s.strip().strip(",").strip() or None


async def _ingest(req: AnalyzeRequest) -> tuple[Listing, list[str]]:
    """Resolve the request into a Listing. Returns (listing, warnings)."""
    raw = req.content.strip()
    warnings: list[str] = []

    # Path A: looks like a URL → fetch + JSON-LD parse first.
    if _URL_RE.match(raw):
        try:
            listing = await listing_parser.parse_url(raw)
        except Exception as e:
            err = str(e)
            if any(h in err for h in _PORTAL_BLOCK_HINTS):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Ce portail bloque les requêtes automatisées. "
                        "Ouvrez l'annonce dans votre navigateur, faites Cmd+A "
                        "puis Cmd+C sur la page, et collez le contenu ici à "
                        "la place de l'URL."
                    ),
                ) from e
            raise HTTPException(
                status_code=422,
                detail=f"Impossible de récupérer l'URL : {err}",
            ) from e

        # Page may be a JS shell (Bien'ici, etc.) — fall through to LLM
        # only if we got nothing useful.
        usable = listing.price_eur and listing.surface_m2 and listing.address_raw
        if not usable:
            raise HTTPException(
                status_code=422,
                detail=(
                    "L'URL a chargé mais ne contient pas les données "
                    "structurées (prix/surface/adresse). C'est typique des "
                    "portails qui rendent côté client. Copiez la page de "
                    "l'annonce (Cmd+A, Cmd+C) et collez le contenu ici."
                ),
            )
        return listing, warnings

    # Path B: pasted text/HTML → LLM extract.
    try:
        listing = await extractor.extract(
            raw, source_url=str(req.source_url) if req.source_url else None
        )
    except extractor.ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return listing, warnings


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    listing, warnings = await _ingest(req)

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

    type_local = "Appartement"
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
