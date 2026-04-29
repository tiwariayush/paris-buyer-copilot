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
import re
from typing import Any
from urllib.parse import urlparse

import extruct
import httpx
from selectolax.parser import HTMLParser

from ..config import settings
from ..models.schemas import Listing

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
    async with httpx.AsyncClient(
        headers={
            "User-Agent": cfg.user_agent,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
        },
        timeout=cfg.request_timeout_s,
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
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
