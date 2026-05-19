"""Detect premium listing attributes (views, light) from text and photos.

DVF comparables rarely encode vue Tour Eiffel or luminosité — these are
parsed from the listing description/title and merged with optional photo
analysis, then passed to the valuation engine as explicit hedonic adjustments.
"""
from __future__ import annotations

import re
from typing import Literal

from ..models.schemas import Listing, PhotoAnalysis, PremiumFeatures

ViewTier = Literal["none", "courtyard", "street", "panoramic", "landmark"]
LightTier = Literal["none", "dark", "average", "bright", "exceptional"]

_VIEW_RANK: dict[ViewTier, int] = {
    "none": 0,
    "courtyard": 1,
    "street": 2,
    "panoramic": 3,
    "landmark": 4,
}

_LIGHT_RANK: dict[LightTier, int] = {
    "none": 0,
    "dark": 1,
    "average": 2,
    "bright": 3,
    "exceptional": 4,
}

# (pattern, view_tier, highlight_fr) — order matters (first match wins per tier upgrade)
_VIEW_RULES: list[tuple[str, ViewTier, str]] = [
  # Landmark / monument views (require explicit "vue" or "view", not just proximity)
    (
        r"(?:vue|view|perspective|aperçu|vis-à-vis\s+sur)[^.]{0,50}tour\s+eiffel",
        "landmark",
        "Vue Tour Eiffel",
    ),
    (
        r"tour\s+eiffel[^.]{0,50}(?:vue|view|dégagée|panoram|imprenable)",
        "landmark",
        "Vue Tour Eiffel",
    ),
    (
        r"(?:vue|view)[^.]{0,50}(?:sacr[ée]e?[\s\-]?c[oœ]ur|notre[\s\-]?dame|arc\s+de\s+triomphe|invalides|panth[ée]on|d[ôo]me\s+des\s+invalides)",
        "landmark",
        "Vue monument",
    ),
    (
        r"(?:vue|view)\s+(?:sur\s+)?(?:la\s+)?(?:seine|paris|toits)",
        "panoramic",
        "Vue dégagée sur Paris",
    ),
    (
        r"vue\s+(?:panoram|imprenable|dégagée|sans\s+vis[\s\-]?à[\s\-]?vis|à\s+couper\s+le\s+souffle)",
        "panoramic",
        "Vue panoramique",
    ),
    (
        r"(?:rooftop|dernier\s+étage).{0,30}(?:terrasse|vue)",
        "panoramic",
        "Dernier étage / terrasse",
    ),
    (
        r"(?:sur\s+)?cour(?:tyard)?|vue\s+cour|donnant\s+sur\s+cour|sur\s+cour\s+intérieure",
        "courtyard",
        "Sur cour",
    ),
]

_LIGHT_RULES: list[tuple[str, LightTier, str]] = [
    (
        r"double\s+exposition|traversant|traversée|exposé(?:e)?\s+(?:est|ouest)\s+et\s+(?:nord|sud)",
        "exceptional",
        "Double exposition",
    ),
    (
        r"très\s+lumineux|exceptionnellement\s+lumineux|baigné(?:e)?\s+de\s+lumière|"
        r"inondé(?:e)?\s+de\s+lumière|lumineux\s+à\s+souhait",
        "exceptional",
        "Très lumineux",
    ),
    (
        r"\blumineux\b|grande\s+luminosité|plein(?:e)?\s+(?:de\s+)?lumière|clair(?:e)?\s+et\s+lumineux",
        "bright",
        "Lumineux",
    ),
    (
        r"plein\s+sud|exposition\s+sud|orienté(?:e)?\s+sud|ensoleillé(?:e)?",
        "bright",
        "Exposition sud",
    ),
    (
        r"sombre|peu\s+lumineux|manque\s+de\s+lumière|sous[\s\-]?éclairé",
        "dark",
        "Peu lumineux",
    ),
]


def _normalize_text(*parts: str | None) -> str:
    blob = " ".join(p for p in parts if p)
    blob = blob.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", blob).strip().lower()


def _best_view(current: ViewTier, candidate: ViewTier) -> ViewTier:
    return candidate if _VIEW_RANK[candidate] > _VIEW_RANK[current] else current


def _best_light(current: LightTier, candidate: LightTier) -> LightTier:
    return candidate if _LIGHT_RANK[candidate] > _LIGHT_RANK[current] else current


def detect_from_text(text: str) -> tuple[ViewTier, LightTier, list[str], list[str]]:
    """Rule-based extraction from French listing copy."""
    if not text or len(text) < 8:
        return "none", "none", [], []

    norm = _normalize_text(text)
    highlights: list[str] = []
    sources: list[str] = []
    view: ViewTier = "none"
    light: LightTier = "none"

    for pattern, tier, label in _VIEW_RULES:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            view = _best_view(view, tier)
            if label not in highlights:
                highlights.append(label)

    for pattern, tier, label in _LIGHT_RULES:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            light = _best_light(light, tier)
            if label not in highlights:
                highlights.append(label)

    if view != "none" or light != "none":
        sources.append("description")

    return view, light, highlights, sources


def _view_from_photo(photo: PhotoAnalysis) -> ViewTier:
    vq = photo.view_quality
    if vq == "landmark":
        return "landmark"
    if vq == "panoramic":
        return "panoramic"
    if vq == "courtyard":
        return "courtyard"
    if vq == "street":
        return "street"
    return "none"


def _light_from_photo(photo: PhotoAnalysis) -> LightTier:
    nl = photo.natural_light
    if nl == "bright":
        return "bright"
    if nl == "dark":
        return "dark"
    if nl == "average":
        return "average"
    return "none"


_PHOTO_VIEW_LABELS: dict[ViewTier, str] = {
    "landmark": "Vue monument (photos)",
    "panoramic": "Vue panoramique (photos)",
    "courtyard": "Sur cour (photos)",
    "street": "Vue rue (photos)",
}

_PHOTO_LIGHT_LABELS: dict[LightTier, str] = {
    "bright": "Luminosité élevée (photos)",
    "dark": "Peu lumineux (photos)",
    "exceptional": "Très lumineux (photos)",
}


def merge_premium(
    listing: Listing,
    photo: PhotoAnalysis | None = None,
) -> PremiumFeatures | None:
    """Combine description/title rules with optional photo analysis."""
    text = _normalize_text(listing.title, listing.description)
    view, light, highlights, sources = detect_from_text(text)

    if photo:
        pv = _view_from_photo(photo)
        pl = _light_from_photo(photo)
        view = _best_view(view, pv)
        light = _best_light(light, pl)
        if pv != "none":
            label = _PHOTO_VIEW_LABELS.get(pv)
            if label and label not in highlights:
                highlights.append(label)
        if pl not in ("none", "average"):
            label = _PHOTO_LIGHT_LABELS.get(pl)
            if label and label not in highlights:
                highlights.append(label)
        if pv != "none" or pl not in ("none", "average"):
            if "photo" not in sources:
                sources.append("photo")

    if view == "none" and light in ("none", "average"):
        return None

    return PremiumFeatures(
        view_tier=view,
        light_tier=light if light != "average" else "none",
        highlights_fr=highlights,
        sources=sources,
    )
