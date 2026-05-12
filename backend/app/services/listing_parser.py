"""Parse a real-estate listing URL into a structured Listing.

Strategy:
1. Fetch the page (single request, with a polite User-Agent).
2. Extract structured data via JSON-LD / microdata / Open Graph (extruct).
3. Per-portal CSS-selector fallback for fields not exposed in JSON-LD
   (notably LeBonCoin, which embeds JSON in __NEXT_DATA__).

All portals (Bien'ici, SeLoger, LeBonCoin, PAP, Logic-Immo) emit some
amount of structured data for SEO; we lean on that to stay legally clean
(no bulk crawl, just one user-pasted URL at a time).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import extruct
import httpx
from selectolax.parser import HTMLParser

from ..config import settings
from ..models.schemas import Listing

log = logging.getLogger(__name__)

_PORTALS = {
    "bienici.com": "Bien'ici",
    "www.bienici.com": "Bien'ici",
    "seloger.com": "SeLoger",
    "www.seloger.com": "SeLoger",
    "leboncoin.fr": "LeBonCoin",
    "www.leboncoin.fr": "LeBonCoin",
    "pap.fr": "PAP",
    "www.pap.fr": "PAP",
    "logic-immo.com": "Logic-Immo",
    "www.logic-immo.com": "Logic-Immo",
}


def detect_portal(url: str) -> str:
    host = urlparse(url).hostname or ""
    return _PORTALS.get(host, host or "unknown")


async def fetch(url: str) -> str:
    cfg = settings()
    host = urlparse(url).hostname or ""
    async with httpx.AsyncClient(
        headers={
            "User-Agent": cfg.user_agent,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
        },
        timeout=cfg.request_timeout_s,
        follow_redirects=True,
    ) as client:
        log.info("listing_fetch_start host=%s url=%s", host, url[:200])
        resp = await client.get(url)
        if resp.status_code >= 400:
            body_preview = (resp.text or "")[:400].replace("\n", " ")
            log.warning(
                "listing_fetch_http_error host=%s status=%s bytes=%s preview=%r",
                host,
                resp.status_code,
                len(resp.content or b""),
                body_preview,
            )
        resp.raise_for_status()
        log.info(
            "listing_fetch_ok host=%s status=%s html_bytes=%s",
            host,
            resp.status_code,
            len(resp.text or ""),
        )
        return resp.text


def _extract_jsonld(html: str, url: str) -> list[dict[str, Any]]:
    try:
        data = extruct.extract(
            html,
            base_url=url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    out.extend(data.get("json-ld", []) or [])
    out.extend(data.get("microdata", []) or [])
    out.extend(data.get("opengraph", []) or [])
    return out


def _flatten_jsonld(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-LD often nests an @graph; flatten it."""
    flat: list[dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, dict) and "@graph" in b:
            for n in b["@graph"]:
                flat.append(n)
        elif isinstance(b, list):
            flat.extend(b)
        else:
            flat.append(b)
    return flat


def _pick_listing_node(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    interesting = (
        "RealEstateListing",
        "Residence",
        "Apartment",
        "House",
        "SingleFamilyResidence",
        "Accommodation",
        "Product",
        "Place",
    )
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("@type") or b.get("type")
        if isinstance(t, list):
            t = t[0] if t else None
        if isinstance(t, str) and t in interesting:
            return b
    return blocks[0] if blocks else None


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        for k in ("value", "@value", "price", "amount"):
            if k in x:
                return _to_float(x[k])
        return None
    s = str(x).replace("\xa0", " ").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _to_int(x: Any) -> int | None:
    f = _to_float(x)
    return int(f) if f is not None else None


def _addr_from_node(node: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (raw, postal_code, city)."""
    a = node.get("address")
    if isinstance(a, list) and a:
        a = a[0]
    if isinstance(a, dict):
        street = a.get("streetAddress") or ""
        city = a.get("addressLocality") or ""
        pc = a.get("postalCode") or None
        raw = ", ".join([s for s in (street, pc, city) if s]).strip(", ") or None
        return raw, pc, city or None
    if isinstance(a, str):
        return a, None, None
    return None, None, None


def _surface_from_node(node: dict[str, Any]) -> float | None:
    fs = node.get("floorSize") or node.get("size")
    if isinstance(fs, dict):
        v = fs.get("value")
        return _to_float(v)
    return _to_float(fs)


def _photos_from_node(node: dict[str, Any]) -> list[str]:
    img = node.get("image") or node.get("photo")
    if not img:
        return []
    if isinstance(img, str):
        return [img]
    if isinstance(img, list):
        out: list[str] = []
        for i in img:
            if isinstance(i, str):
                out.append(i)
            elif isinstance(i, dict) and i.get("url"):
                out.append(i["url"])
        return out
    if isinstance(img, dict) and img.get("url"):
        return [img["url"]]
    return []


def _from_jsonld(node: dict[str, Any]) -> dict[str, Any]:
    """Map a generic JSON-LD listing/product node onto our Listing fields."""
    out: dict[str, Any] = {}
    out["title"] = node.get("name") or node.get("headline")
    out["description"] = node.get("description")
    raw, pc, city = _addr_from_node(node)
    out["address_raw"] = raw
    out["postal_code"] = pc
    out["city"] = city
    offers = node.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        out["price_eur"] = _to_float(offers.get("price"))
    elif "price" in node:
        out["price_eur"] = _to_float(node.get("price"))
    out["surface_m2"] = _surface_from_node(node)
    out["rooms"] = _to_int(
        node.get("numberOfRooms")
        or node.get("numberOfRoomsTotal")
        or node.get("rooms")
    )
    out["bedrooms"] = _to_int(
        node.get("numberOfBedrooms") or node.get("bedrooms")
    )
    out["photos"] = _photos_from_node(node)
    return out


# ------------------------------- per-portal --------------------------------

def _from_leboncoin(html: str) -> dict[str, Any]:
    """LeBonCoin embeds full ad data in window.__NEXT_DATA__."""
    parser = HTMLParser(html)
    node = parser.css_first('script#__NEXT_DATA__')
    if not node:
        return {}
    try:
        data = json.loads(node.text())
    except Exception:
        return {}
    try:
        ad = (
            data.get("props", {})
            .get("pageProps", {})
            .get("ad")
            or data.get("props", {}).get("pageProps", {}).get("classified")
        )
    except Exception:
        ad = None
    if not isinstance(ad, dict):
        return {}
    out: dict[str, Any] = {}
    out["title"] = ad.get("subject")
    out["description"] = ad.get("body")
    out["price_eur"] = _to_float(ad.get("price") or (ad.get("price_cents") or 0) / 100)
    out["postal_code"] = (ad.get("location") or {}).get("zipcode")
    out["city"] = (ad.get("location") or {}).get("city")
    addr = (ad.get("location") or {}).get("address")
    if addr:
        out["address_raw"] = addr
    for attr in ad.get("attributes", []) or []:
        key = (attr.get("key") or "").lower()
        val = attr.get("value") or attr.get("value_label")
        if key in {"square", "surface"}:
            out["surface_m2"] = _to_float(val)
        elif key in {"rooms", "nb_rooms"}:
            out["rooms"] = _to_int(val)
        elif key in {"bedrooms", "nb_bedrooms"}:
            out["bedrooms"] = _to_int(val)
        elif key == "energy_rate":
            out["dpe_class"] = (val or "").upper().strip() or None
        elif key == "floor_number":
            out["floor"] = _to_int(val)
        elif key == "elevator":
            out["has_elevator"] = (val or "").lower() in ("1", "true", "oui", "yes")
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _from_bienici(html: str) -> dict[str, Any]:
    """Bien'ici exposes JSON-LD + a globalAd JSON blob."""
    out: dict[str, Any] = {}
    m = re.search(
        r"window\.__APP_INITIAL_STATE__\s*=\s*JSON\.parse\((['\"])(?P<json>.*?)\1\s*\)",
        html,
        flags=re.DOTALL,
    )
    if m:
        try:
            payload = json.loads(json.loads('"' + m.group("json") + '"'))
            ad = (
                payload.get("adDetail", {}).get("ad")
                or payload.get("ad")
                or {}
            )
            if ad:
                out.setdefault("dpe_class", ad.get("energyClassification"))
                out.setdefault("floor", _to_int(ad.get("floor")))
                out.setdefault("has_elevator", ad.get("hasLift"))
        except Exception:
            pass
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _bienici_ad_id_from_url(url: str) -> str | None:
    """Extract the ad ID from a Bien'ici listing URL."""
    m = re.search(r"/annonce/[^/]+/[^/]+/[^/]+/[^/]+/([\w-]+)", url)
    return m.group(1) if m else None


def _from_bienici_api(ad: dict[str, Any]) -> dict[str, Any]:
    """Map Bien'ici JSON API response to our Listing fields."""
    out: dict[str, Any] = {}
    out["title"] = ad.get("title")
    out["description"] = ad.get("description")
    out["price_eur"] = _to_float(ad.get("price"))
    out["surface_m2"] = _to_float(ad.get("surfaceArea"))
    out["rooms"] = _to_int(ad.get("roomsQuantity"))
    out["bedrooms"] = _to_int(ad.get("bedroomsQuantity"))
    out["postal_code"] = ad.get("postalCode")
    out["city"] = ad.get("city")
    out["dpe_class"] = ad.get("energyClassification")
    out["floor"] = _to_int(ad.get("floor"))
    out["has_elevator"] = ad.get("hasElevator")

    district = ad.get("district") or {}
    district_name = district.get("libelle") or district.get("name") or ""
    city = ad.get("city") or ""
    pc = ad.get("postalCode") or ""
    parts = [p for p in (district_name, city, pc) if p]
    out["address_raw"] = ", ".join(parts) if parts else None

    # Try to get street from title (often "... – RUE DE X / QUARTIER Y")
    title = ad.get("title") or ""
    addr_m = re.search(
        r"(?:rue|avenue|bd|boulevard|place|impasse|quai|passage)"
        r"\s+[A-Za-zÀ-ÖØ-öø-ÿ' \-]+",
        title,
        flags=re.IGNORECASE,
    )
    if addr_m:
        out["address_raw"] = f"{addr_m.group(0).strip()}, {pc}" if pc else addr_m.group(0).strip()

    photos = []
    for p in ad.get("photos", []):
        url = p.get("url") or p.get("url_photo")
        if url:
            photos.append(url)
    if photos:
        out["photos"] = photos

    return {k: v for k, v in out.items() if v not in (None, "", [])}


async def _fetch_bienici_api(ad_id: str) -> dict[str, Any] | None:
    """Fetch listing data from Bien'ici's JSON API."""
    cfg = settings()
    api_url = f"https://www.bienici.com/realEstateAd.json?id={ad_id}"
    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": cfg.user_agent,
                "Accept": "application/json",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
            },
            timeout=cfg.request_timeout_s,
            follow_redirects=True,
        ) as client:
            resp = await client.get(api_url)
            if resp.status_code == 200:
                log.info("bienici_api_ok ad_id=%s", ad_id)
                return resp.json()
            log.warning("bienici_api_error ad_id=%s status=%s", ad_id, resp.status_code)
    except Exception as exc:
        log.warning("bienici_api_exception ad_id=%s err=%s", ad_id, exc)
    return None


def _from_seloger(html: str) -> dict[str, Any]:
    """SeLoger embeds classified data in __UFRN_LIFECYCLE_SERVERREQUEST__."""
    m = re.search(
        r'window\["__UFRN_LIFECYCLE_SERVERREQUEST__"\]\s*=\s*JSON\.parse\("(.*?)"\);',
        html,
        flags=re.DOTALL,
    )
    if not m:
        return {}
    try:
        unescaped = m.group(1).encode().decode("unicode_escape")
        data = json.loads(unescaped)
    except Exception:
        return {}

    classified = data.get("app_cldp", {}).get("data", {}).get("classified", {})
    if not classified:
        return {}

    sections = classified.get("sections", {})
    tracking = classified.get("tracking", {})
    raw_data = classified.get("rawData", {})
    out: dict[str, Any] = {}

    # Title from mainDescription or hardFacts
    main_desc = sections.get("mainDescription", {})
    out["title"] = main_desc.get("headline")

    # Description
    desc_section = sections.get("description", {})
    out["description"] = desc_section.get("description")

    # Price: extract from tracking (cleanest) or price section aria label
    items = tracking.get("av_items", [])
    if items and isinstance(items, list):
        out["price_eur"] = _to_float(items[0].get("price"))
    if not out.get("price_eur"):
        price_section = sections.get("price", {})
        base_price = price_section.get("base", {}).get("main", {})
        aria = base_price.get("value", {}).get("main", {}).get("ariaLabel", "")
        out["price_eur"] = _to_float(re.sub(r"[^\d]", "", aria)) if aria else None

    # Surface, rooms, bedrooms from hardFacts "facts" array
    hard_facts = sections.get("hardFacts", {})
    for fact in hard_facts.get("facts", []):
        ftype = fact.get("type", "")
        split_val = fact.get("splitValue", "")
        if ftype in ("livingSpace", "surface"):
            out["surface_m2"] = _to_float(split_val)
        elif ftype == "numberOfRooms":
            out["rooms"] = _to_int(split_val)
        elif ftype == "numberOfBedrooms":
            out["bedrooms"] = _to_int(split_val)

    # Location
    loc = sections.get("location", {})
    addr = loc.get("address", {})
    out["postal_code"] = addr.get("zipCode")
    city = addr.get("city", "")
    district = addr.get("district", "")
    out["city"] = city
    parts = [p for p in (district, city, addr.get("zipCode", "")) if p]
    out["address_raw"] = ", ".join(parts) if parts else None

    # DPE: from energy section or tracking
    energy = sections.get("energy", {})
    cert = energy.get("certificate", {})
    out["dpe_class"] = cert.get("value") if cert.get("value") else None
    if not out.get("dpe_class"):
        out["dpe_class"] = tracking.get("av_energy_certificate")

    # Floor and elevator from features preview
    features = sections.get("features", {})
    for feat in features.get("preview", []):
        icon = feat.get("icon", "")
        val = feat.get("value", "")
        if icon == "elevator":
            out["has_elevator"] = True
        elif icon == "floors":
            floor_m = re.match(r"(\d+)", val)
            if floor_m:
                out["floor"] = int(floor_m.group(1))

    # Photos
    gallery = sections.get("gallery", {})
    photos = []
    for img in gallery.get("images", []):
        url = img.get("url")
        if url:
            photos.append(url)
    if photos:
        out["photos"] = photos

    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _from_pap(html: str) -> dict[str, Any]:
    """PAP is server-rendered with structured HTML elements."""
    parser = HTMLParser(html)
    out: dict[str, Any] = {}

    # Rooms, bedrooms, surface from .item-tags <li> elements
    tags_ul = parser.css_first(".item-tags")
    if tags_ul:
        for li in tags_ul.css("li"):
            text = (li.text() or "").strip()
            m = re.match(r"(\d+)\s*pi[èe]ces?", text, re.IGNORECASE)
            if m:
                out["rooms"] = int(m.group(1))
                continue
            m = re.match(r"(\d+)\s*chambres?", text, re.IGNORECASE)
            if m:
                out["bedrooms"] = int(m.group(1))
                continue
            m = re.match(r"([\d.,]+)\s*m[²2]", text)
            if m:
                out["surface_m2"] = float(m.group(1).replace(",", "."))
                continue

    # DPE: the active <li> inside .energy-indice
    energy_div = parser.css_first(".energy-indice")
    if energy_div:
        active = energy_div.css_first("li.active")
        if active:
            letter = (active.text() or "").strip().upper()
            if letter in "ABCDEFG":
                out["dpe_class"] = letter

    # Floor and elevator from description text
    desc_div = parser.css_first(".item-description")
    desc_text = (desc_div.text() if desc_div else "") or ""
    m = re.search(r"(\d{1,2})\s*[eè](?:me)?\s*[ée]tage", desc_text, re.IGNORECASE)
    if m:
        out["floor"] = int(m.group(1))
    if re.search(r"sans\s+ascenseur|pas\s+d['\xe9e]\s*ascenseur", desc_text, re.IGNORECASE):
        out["has_elevator"] = False
    elif re.search(r"\bascenseur\b", desc_text, re.IGNORECASE):
        out["has_elevator"] = True

    return {k: v for k, v in out.items() if v not in (None, "", [])}


# ------------------------------- public ------------------------------------

def parse_html(html: str, url: str) -> Listing:
    portal = detect_portal(url)
    blocks = _flatten_jsonld(_extract_jsonld(html, url))
    node = _pick_listing_node(blocks) or {}
    base = _from_jsonld(node) if node else {}

    portal_extra: dict[str, Any] = {}
    if portal == "LeBonCoin":
        portal_extra = _from_leboncoin(html)
    elif portal == "Bien'ici":
        portal_extra = _from_bienici(html)
    elif portal == "SeLoger":
        portal_extra = _from_seloger(html)
    elif portal == "PAP":
        portal_extra = _from_pap(html)

    # Heuristic DPE extraction from description if still missing.
    if not base.get("dpe_class") and not portal_extra.get("dpe_class"):
        text = base.get("description") or ""
        m = re.search(r"DPE\s*[:\-]?\s*([A-G])\b", text, flags=re.IGNORECASE)
        if m:
            base["dpe_class"] = m.group(1).upper()

    merged: dict[str, Any] = {**base, **portal_extra}
    merged = {k: v for k, v in merged.items() if v not in (None, "", [])}

    return Listing(
        source_url=url,
        portal=portal,
        title=merged.get("title"),
        price_eur=merged.get("price_eur"),
        surface_m2=merged.get("surface_m2"),
        rooms=merged.get("rooms"),
        bedrooms=merged.get("bedrooms"),
        address_raw=merged.get("address_raw"),
        postal_code=merged.get("postal_code"),
        city=merged.get("city"),
        description=merged.get("description"),
        photos=merged.get("photos") or [],
        dpe_class=merged.get("dpe_class"),
        floor=merged.get("floor"),
        has_elevator=merged.get("has_elevator"),
    )


async def parse_url(url: str) -> Listing:
    html = await fetch(url)
    return parse_html(html, url)
