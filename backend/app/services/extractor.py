"""LLM-powered listing extraction from any blob of text.

Use case: the user pastes the visible content of a listing page that we can't
fetch server-side (SeLoger, LeBonCoin, Bien'ici, PAP all block cloud IPs in
2026). The pasted blob may be plain copy-paste (`Cmd+A Cmd+C`), HTML, or a
markdown-ish dump — we let the LLM extract structured fields.

We use OpenAI's structured outputs to guarantee a typed result. Falls back
to a coarse regex-based extractor when no API key is set, so the demo
remains usable.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from ..models.schemas import Listing

SYSTEM_PROMPT = """\
You are a real-estate listing parser for Paris properties. Given the raw \
text or HTML of a listing page (often messy, in French), extract the \
structured fields. Be precise:
- price_eur: TOTAL ASKING PRICE in euros (not monthly rent, not €/m²).
  If the listing is a rental ("location", "à louer", "/mois"), return null.
- surface_m2: HABITABLE surface in m² (not lot size).
- address_raw: street + number when visible. Otherwise neighborhood + arr.
- postal_code: 5 digits if visible (75001..75020 for Paris).
- rooms: total room count ("pièces" not "chambres").
- bedrooms: bedroom count ("chambres").
- dpe_class: single letter A-G if a DPE is mentioned. Look for "DPE", \
  "GES", "étiquette énergie", or A/B/C/D/E/F/G in an energy context.
- floor: integer (0 = ground floor, "rdc"/"rez-de-chaussée").
- has_elevator: true if "ascenseur" mentioned positively, false if \
  "sans ascenseur"/"pas d'ascenseur", null otherwise.
- title: short headline of the listing if available.

Return null for any field you can't confidently determine. Don't guess.\
"""

_EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "price_eur": {"type": ["number", "null"]},
        "surface_m2": {"type": ["number", "null"]},
        "rooms": {"type": ["integer", "null"]},
        "bedrooms": {"type": ["integer", "null"]},
        "address_raw": {"type": ["string", "null"]},
        "postal_code": {"type": ["string", "null"]},
        "dpe_class": {"type": ["string", "null"], "enum": ["A", "B", "C", "D", "E", "F", "G", None]},
        "floor": {"type": ["integer", "null"]},
        "has_elevator": {"type": ["boolean", "null"]},
        "is_rental": {"type": "boolean"},
        "rejection_reason": {"type": ["string", "null"]},
    },
    "required": [
        "title", "price_eur", "surface_m2", "rooms", "bedrooms",
        "address_raw", "postal_code", "dpe_class", "floor",
        "has_elevator", "is_rental", "rejection_reason",
    ],
}


class ExtractionError(Exception):
    """Raised when the listing can't be reliably extracted."""


def _regex_fallback(text: str) -> dict[str, Any]:
    """Best-effort regex extraction when no OpenAI key is configured."""
    out: dict[str, Any] = {}
    # Price
    m = re.search(
        r"(\d[\d\s\u00a0]*\d|\d+)\s*(?:€|EUR|euros?)",
        text, flags=re.IGNORECASE,
    )
    if m:
        out["price_eur"] = float(re.sub(r"\D", "", m.group(1)) or 0) or None
    # Surface
    m = re.search(r"(\d{2,4}(?:[.,]\d+)?)\s*m(?:²|2|\u00b2)", text)
    if m:
        out["surface_m2"] = float(m.group(1).replace(",", "."))
    # Rooms
    m = re.search(r"(\d{1,2})\s*pi[èe]ces?\b", text, flags=re.IGNORECASE)
    if m:
        out["rooms"] = int(m.group(1))
    # Postal code (Paris 75xxx)
    m = re.search(r"\b(75\d{3})\b", text)
    if m:
        out["postal_code"] = m.group(1)
    # Address: try "Adresse:" / "Localisation:" prefix first; fall back to
    # the first "<num> rue|avenue|boulevard|..." pattern.
    m = re.search(
        r"(?:Adresse|Localisation)\s*:\s*([^\n]{6,200})",
        text, flags=re.IGNORECASE,
    )
    if m:
        out["address_raw"] = m.group(1).strip().strip(".,")
    else:
        m = re.search(
            r"\b(\d{1,4}(?:\s*(?:bis|ter))?\s+"
            r"(?:rue|avenue|av\.|bd|boulevard|place|impasse|allée|allee|"
            r"quai|cours|passage|villa|chemin|sentier|square|rond[\s\-]?point)"
            r"\s+[A-Za-zÀ-ÖØ-öø-ÿ' \-]{3,80})",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            out["address_raw"] = re.sub(r"\s+", " ", m.group(1)).strip(".,")
    # DPE
    m = re.search(
        r"\bDPE\b[^A-G]{0,20}([A-G])\b",
        text, flags=re.IGNORECASE,
    )
    if m:
        out["dpe_class"] = m.group(1).upper()
    # Floor
    m = re.search(r"(\d{1,2})\s*[eè]?(?:me)?\s*[ée]tage\b", text, flags=re.IGNORECASE)
    if m:
        out["floor"] = int(m.group(1))
    # Elevator
    if re.search(r"sans\s+ascenseur|pas\s+d['e]\s*ascenseur", text, flags=re.IGNORECASE):
        out["has_elevator"] = False
    elif re.search(r"\bascenseur\b", text, flags=re.IGNORECASE):
        out["has_elevator"] = True
    out["is_rental"] = bool(
        re.search(r"\b(location|à\s*louer|/\s*mois|\bloyer\b)", text, flags=re.IGNORECASE)
    )
    return out


async def extract(text: str, source_url: str | None = None) -> Listing:
    """Extract a Listing from a blob of pasted listing content.

    Raises ExtractionError if the result isn't usable (missing price/surface,
    detected as a rental, etc.).
    """
    if not text or len(text) < 60:
        raise ExtractionError(
            "Le texte collé est trop court. Copiez la page complète de l'annonce "
            "(Cmd+A puis Cmd+C sur l'annonce, puis collez ici)."
        )

    cfg = settings()
    data: dict[str, Any] = {}

    if cfg.openai_api_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=cfg.openai_api_key)
            # Trim very long pastes to keep latency + cost predictable.
            blob = text if len(text) < 60_000 else text[:60_000]
            resp = await client.chat.completions.create(
                model=cfg.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": blob},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "listing_extract",
                        "schema": _EXTRACT_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0.0,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            data = {"_llm_error": str(e), **_regex_fallback(text)}
    else:
        data = _regex_fallback(text)

    if data.get("is_rental"):
        raise ExtractionError(
            "Cette annonce semble être une location. Le copilote ne couvre que "
            "les ventes (les comparables DVF n'existent que pour les transactions)."
        )

    price = data.get("price_eur")
    surface = data.get("surface_m2")
    if not price or price < 30_000:
        raise ExtractionError(
            "Aucun prix de vente plausible trouvé. Vérifiez que l'annonce "
            "contient bien un prix d'achat (et pas seulement un loyer mensuel)."
        )
    if not surface or surface < 8:
        raise ExtractionError(
            "Aucune surface habitable plausible trouvée. Recopiez la zone "
            "de l'annonce qui contient les m²."
        )
    if not data.get("address_raw") and not data.get("postal_code"):
        raise ExtractionError(
            "Adresse introuvable. Incluez la zone 'localisation' / 'quartier' "
            "de l'annonce dans votre copie, ou ajoutez un code postal."
        )

    return Listing(
        source_url=source_url or "https://manual.entry/",
        portal="paste",
        title=data.get("title"),
        price_eur=price,
        surface_m2=surface,
        rooms=data.get("rooms"),
        bedrooms=data.get("bedrooms"),
        address_raw=data.get("address_raw"),
        postal_code=data.get("postal_code"),
        city=None,
        description=text[:500] if len(text) > 500 else text,
        photos=[],
        dpe_class=data.get("dpe_class"),
        floor=data.get("floor"),
        has_elevator=data.get("has_elevator"),
    )
