"""POST /analyze — paste a listing URL **or** the listing's text/HTML."""
from __future__ import annotations

import json
import logging
import math
import re
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..models.schemas import AnalyzeRequest, AnalyzeResponse, Listing
from ..services import (
    ai,
    dpe,
    dvf,
    extractor,
    geocoder,
    listing_parser,
    market_index,
    neighborhood,
    photo_analysis,
    quality,
    valuation,
)

router = APIRouter()

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"^\s*https?://[^\s]+\s*$", re.IGNORECASE)
_PORTAL_BLOCK_HINTS = (
    "403", "Forbidden", "DataDome", "CloudFront", "captcha",
    "blocked", "Access Denied", "/jail",
)


def _listing_usable(listing: Listing) -> bool:
    return bool(
        listing.price_eur and listing.surface_m2 and listing.address_raw
    )


def _merge_listings(parsed: Listing, extracted: Listing) -> Listing:
    """Prefer structured SEO fields, fill gaps from HTML/text extraction."""

    def pick_str(a: str | None, b: str | None) -> str | None:
        return a if a and str(a).strip() else (b if b and str(b).strip() else None)

    def pick_num(a: float | int | None, b: float | int | None) -> float | int | None:
        return a if a not in (None, 0) else b

    def pick_int(a: int | None, b: int | None) -> int | None:
        return a if a is not None else b

    desc_p = (parsed.description or "").strip()
    desc_e = (extracted.description or "").strip()
    description = desc_p if len(desc_p) >= len(desc_e) else desc_e
    if not description:
        description = pick_str(parsed.description, extracted.description)

    photos = parsed.photos if parsed.photos else extracted.photos

    return Listing(
        source_url=parsed.source_url,
        portal=parsed.portal,
        title=pick_str(parsed.title, extracted.title),
        price_eur=pick_num(parsed.price_eur, extracted.price_eur),
        surface_m2=pick_num(parsed.surface_m2, extracted.surface_m2),
        rooms=pick_int(parsed.rooms, extracted.rooms),
        bedrooms=pick_int(parsed.bedrooms, extracted.bedrooms),
        address_raw=pick_str(parsed.address_raw, extracted.address_raw),
        postal_code=pick_str(parsed.postal_code, extracted.postal_code),
        city=pick_str(parsed.city, extracted.city),
        description=description,
        photos=photos,
        dpe_class=pick_str(parsed.dpe_class, extracted.dpe_class),
        floor=pick_int(parsed.floor, extracted.floor),
        has_elevator=(
            parsed.has_elevator
            if parsed.has_elevator is not None
            else extracted.has_elevator
        ),
    )


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Approximate distance in meters between two WGS-84 points."""
    R = 6_371_000
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fill_distances(
    comps: list,
    target_lon: float,
    target_lat: float,
) -> None:
    """Ensure every comp has distance_m filled relative to the target location."""
    for c in comps:
        if c.distance_m is not None:
            continue
        if c.longitude is not None and c.latitude is not None:
            c.distance_m = round(
                _haversine_m(target_lon, target_lat, c.longitude, c.latitude), 1
            )


def _voie_from_address(addr: str | None) -> str | None:
    """Best-effort extraction of street name as DVF stores it (uppercase)."""
    if not addr:
        return None
    s = addr.upper()
    s = re.sub(r"^\s*\d+[A-Z]?\s*(BIS|TER|QUATER)?\s*[,]?\s*", "", s)
    s = re.split(r",\s*\d{5}", s)[0]
    return s.strip().strip(",").strip() or None


async def _ingest(
    req: AnalyzeRequest, *, trace_id: str | None = None
) -> tuple[Listing, list[str]]:
    """Resolve the request into a Listing. Returns (listing, warnings)."""
    raw = req.content.strip()
    warnings: list[str] = []
    tid = trace_id or "-"

    # Path A: URL → download HTML once, structured parse, then extract from HTML.
    if _URL_RE.match(raw):
        url_str = raw.strip()
        log.info(
            "ingest_url trace_id=%s url=%s",
            tid,
            url_str[:220],
        )
        try:
            html = await listing_parser.fetch(url_str)
        except Exception as e:
            err = str(e)
            log.warning(
                "ingest_fetch_failed trace_id=%s err_type=%s err=%s",
                tid,
                type(e).__name__,
                err[:500],
            )
            if any(h in err for h in _PORTAL_BLOCK_HINTS):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Ce portail bloque les requêtes automatisées depuis nos "
                        "serveurs. En secours : ouvrez l'annonce dans votre "
                        "navigateur, Cmd+A puis Cmd+C, et collez le texte ici."
                    ),
                ) from e
            raise HTTPException(
                status_code=422,
                detail=f"Impossible de récupérer l'URL : {err}",
            ) from e

        listing_struct = listing_parser.parse_html(html, url_str)
        log.info(
            "ingest_struct_parse trace_id=%s portal=%s price=%s surface=%s addr=%s",
            tid,
            listing_struct.portal,
            listing_struct.price_eur,
            listing_struct.surface_m2,
            (listing_struct.address_raw or "")[:80] or None,
        )
        if _listing_usable(listing_struct):
            log.info("ingest_ok trace_id=%s path=structured_only", tid)
            return listing_struct, warnings

        # Bien'ici API fallback: the HTML is a JS shell, but the JSON API
        # returns full listing data without needing a browser.
        if listing_struct.portal == "Bien'ici":
            ad_id = listing_parser._bienici_ad_id_from_url(url_str)
            if ad_id:
                log.info("ingest_bienici_api trace_id=%s ad_id=%s", tid, ad_id)
                api_data = await listing_parser._fetch_bienici_api(ad_id)
                if api_data:
                    from ..models.schemas import Listing
                    api_fields = listing_parser._from_bienici_api(api_data)
                    listing_api = Listing(
                        source_url=url_str,
                        portal="Bien'ici",
                        title=api_fields.get("title"),
                        price_eur=api_fields.get("price_eur"),
                        surface_m2=api_fields.get("surface_m2"),
                        rooms=api_fields.get("rooms"),
                        bedrooms=api_fields.get("bedrooms"),
                        address_raw=api_fields.get("address_raw"),
                        postal_code=api_fields.get("postal_code"),
                        city=api_fields.get("city"),
                        description=api_fields.get("description"),
                        photos=api_fields.get("photos", []),
                        dpe_class=api_fields.get("dpe_class"),
                        floor=api_fields.get("floor"),
                        has_elevator=api_fields.get("has_elevator"),
                    )
                    if _listing_usable(listing_api):
                        log.info("ingest_ok trace_id=%s path=bienici_api", tid)
                        return listing_api, warnings

        # Same HTML, second pass: LLM / regex on the downloaded document
        # (works when SEO tags are missing but body or __NEXT_DATA__ still
        # contains the ad).
        log.info(
            "ingest_fallback_extract trace_id=%s html_len=%s",
            tid,
            len(html),
        )
        try:
            listing_llm = await extractor.extract(html, source_url=url_str)
        except extractor.ExtractionError as exc:
            log.warning(
                "ingest_extract_failed trace_id=%s (structured was incomplete)",
                tid,
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{exc}"
                    if str(exc)
                    else (
                        "L'URL a bien été téléchargée, mais prix, surface et adresse "
                        "n'ont pas été retrouvés dans le HTML reçu. Souvent le portail "
                        "ne renvoie qu'une coquille vide côté serveur, ou bloque "
                        "l'accès automatisé : copiez alors la page visible "
                        "(Cmd+A, Cmd+C) et collez le texte ici."
                    )
                ),
            ) from exc

        merged = _merge_listings(listing_struct, listing_llm)
        if not _listing_usable(merged):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Impossible de combiner les données extraites de la page. "
                    "Collez le contenu visible de l'annonce (Cmd+A, Cmd+C)."
                ),
            )
        warnings.append(
            "Complément : certaines informations viennent de l'analyse du "
            "HTML téléchargé (données structurées incomplètes sur la page)."
        )
        log.info("ingest_ok trace_id=%s path=structured_plus_extract", tid)
        return merged, warnings

    # Path B: pasted text/HTML → LLM extract.
    log.info(
        "ingest_paste trace_id=%s content_len=%s source_url=%s",
        tid,
        len(raw),
        str(req.source_url) if req.source_url else None,
    )
    try:
        listing = await extractor.extract(
            raw, source_url=str(req.source_url) if req.source_url else None
        )
    except extractor.ExtractionError as e:
        log.warning("ingest_paste_extract_failed trace_id=%s err=%s", tid, str(e)[:400])
        raise HTTPException(status_code=422, detail=str(e)) from e
    log.info("ingest_ok trace_id=%s path=paste_extract", tid)
    return listing, warnings


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, response: Response) -> AnalyzeResponse:
    trace_id = uuid.uuid4().hex[:10]
    response.headers["X-Trace-Id"] = trace_id
    mode = "url" if _URL_RE.match(req.content.strip()) else "paste"
    log.info(
        "analyze_start trace_id=%s mode=%s content_len=%d",
        trace_id,
        mode,
        len(req.content),
    )
    try:
        listing, warnings = await _ingest(req, trace_id=trace_id)
    except HTTPException as e:
        log.warning(
            "analyze_http_error trace_id=%s status=%s detail=%s",
            trace_id,
            e.status_code,
            e.detail if isinstance(e.detail, str) else str(e.detail)[:500],
        )
        raise

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

    if location:
        _fill_distances(comps, location.lon, location.lat)

    building_hist: list = []
    if location and location.id_parcelle:
        building_hist = dvf.building_history(location.id_parcelle)

    dpe_report = None
    try:
        dpe_report = await dpe.lookup(
            listing.address_raw, listing.postal_code, surface=listing.surface_m2
        )
    except Exception as e:
        warnings.append(f"DPE lookup failed: {e}")

    photo_result = None
    try:
        photo_result = await photo_analysis.analyze_photos(listing.photos)
    except Exception as e:
        warnings.append(f"Photo analysis failed: {e}")

    renovation_state = photo_result.renovation_state if photo_result else None

    if dpe_report and dpe_report.dpe_class and not listing.dpe_class:
        listing.dpe_class = dpe_report.dpe_class

    val = valuation.value_listing(
        listing, comps, base_tier, renovation_state=renovation_state
    )

    delta_eur = None
    delta_pct = None
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

    quality_warnings = quality.run_all_checks(
        listing, location, val, comps, dpe_report
    )
    for qw in quality_warnings:
        warnings.append(f"[{qw.severity}] {qw.message_fr}")

    mkt_index = market_index.compute_market_position(
        listing.price_eur, listing.surface_m2, code_postal
    )

    log.info(
        "analyze_done trace_id=%s fair_value_eur=%s n_comps=%s tier=%s "
        "n_warnings=%d n_quality_warnings=%d",
        trace_id,
        val.fair_value_eur,
        val.n_comps,
        val.base_tier,
        len(warnings),
        len(quality_warnings),
    )

    return AnalyzeResponse(
        listing=listing,
        location=location,
        valuation=val,
        comps=comps[:30],
        building_history=building_hist[:20],
        dpe=dpe_report,
        neighborhood=nbh,
        negotiation=negotiation,
        market_index=mkt_index,
        photo_analysis=photo_result,
        delta_pct=delta_pct,
        delta_eur=delta_eur,
        warnings=warnings,
    )


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/analyze/stream")
async def analyze_stream(request: Request) -> StreamingResponse:
    """SSE variant: emits 'listing' as soon as parsed, then 'verdict' with full result."""
    body = await request.json()
    req = AnalyzeRequest(**body)

    async def event_generator():
        trace_id = uuid.uuid4().hex[:10]
        mode = "url" if _URL_RE.match(req.content.strip()) else "paste"
        log.info(
            "analyze_stream_start trace_id=%s mode=%s content_len=%d",
            trace_id, mode, len(req.content),
        )

        try:
            listing, warnings = await _ingest(req, trace_id=trace_id)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            yield _sse_event("error", {"detail": detail, "status": e.status_code})
            return

        yield _sse_event("listing", listing.model_dump(mode="json"))

        if await request.is_disconnected():
            return

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

        if location:
            _fill_distances(comps, location.lon, location.lat)

        building_hist: list = []
        if location and location.id_parcelle:
            building_hist = dvf.building_history(location.id_parcelle)

        dpe_report = None
        try:
            dpe_report = await dpe.lookup(
                listing.address_raw, listing.postal_code, surface=listing.surface_m2
            )
        except Exception as e:
            warnings.append(f"DPE lookup failed: {e}")

        photo_result = None
        try:
            photo_result = await photo_analysis.analyze_photos(listing.photos)
        except Exception as e:
            warnings.append(f"Photo analysis failed: {e}")

        renovation_state = photo_result.renovation_state if photo_result else None

        if dpe_report and dpe_report.dpe_class and not listing.dpe_class:
            listing.dpe_class = dpe_report.dpe_class

        val = valuation.value_listing(
            listing, comps, base_tier, renovation_state=renovation_state
        )

        delta_eur = None
        delta_pct = None
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

        quality_warnings = quality.run_all_checks(
            listing, location, val, comps, dpe_report
        )
        for qw in quality_warnings:
            warnings.append(f"[{qw.severity}] {qw.message_fr}")

        mkt_index = market_index.compute_market_position(
            listing.price_eur, listing.surface_m2, code_postal
        )

        log.info(
            "analyze_stream_done trace_id=%s fair_value=%s n_comps=%s tier=%s",
            trace_id, val.fair_value_eur, val.n_comps, val.base_tier,
        )

        result = AnalyzeResponse(
            listing=listing,
            location=location,
            valuation=val,
            comps=comps[:30],
            building_history=building_hist[:20],
            dpe=dpe_report,
            neighborhood=nbh,
            negotiation=negotiation,
            market_index=mkt_index,
            photo_analysis=photo_result,
            delta_pct=delta_pct,
            delta_eur=delta_eur,
            warnings=warnings,
        )
        yield _sse_event("verdict", result.model_dump(mode="json"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
