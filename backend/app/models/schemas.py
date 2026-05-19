"""Pydantic request/response schemas exposed via OpenAPI."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AnalyzeRequest(BaseModel):
    """Single field, two ways:
    - URL → backend downloads HTML, parses JSON-LD / portal blobs, then
      if needed runs the same HTML through the text extractor (LLM or regex).
    - Plain text/HTML (paste) → backend runs the extractor only.
    The frontend picks based on what looks like a URL.
    """
    content: str = Field(..., min_length=4)
    source_url: HttpUrl | None = None  # preserved when content is a paste


class Listing(BaseModel):
    """Structured listing extracted from a paste-in URL."""
    source_url: HttpUrl
    portal: str
    title: str | None = None
    price_eur: float | None = None
    surface_m2: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    address_raw: str | None = None
    postal_code: str | None = None
    city: str | None = None
    description: str | None = None
    photos: list[str] = Field(default_factory=list)
    dpe_class: str | None = None
    floor: int | None = None
    has_elevator: bool | None = None


class GeoLocation(BaseModel):
    lat: float
    lon: float
    address_normalized: str
    score: float | None = None
    id_parcelle: str | None = None
    code_iris: str | None = None
    nom_iris: str | None = None
    code_commune: str
    code_postal: str | None = None


class Comp(BaseModel):
    """A single comparable transaction from DVF."""
    id_mutation: str
    date_mutation: date
    valeur_fonciere: float
    surface_reelle_bati: float | None
    nombre_pieces_principales: int | None
    type_local: str | None
    adresse: str | None
    code_postal: str | None
    id_parcelle: str | None
    longitude: float | None
    latitude: float | None
    price_per_m2: float | None
    tier: Literal["building", "street", "iris"]
    distance_m: float | None = None


class DPEReport(BaseModel):
    dpe_class: str | None = None
    ges_class: str | None = None
    consumption_kwh_m2_year: float | None = None
    emissions_kgco2_m2_year: float | None = None
    surface_m2: float | None = None
    year_certified: int | None = None
    address: str | None = None


class Valuation(BaseModel):
    fair_value_eur: float | None
    fair_value_low_eur: float | None
    fair_value_high_eur: float | None
    price_per_m2_estimate: float | None
    confidence: Literal["low", "medium", "high"]
    n_comps: int
    base_tier: Literal["building", "street", "iris", "none"]
    adjustments: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""


class Neighborhood(BaseModel):
    iris_code: str | None = None
    iris_name: str | None = None
    median_household_income_eur: float | None = None
    population: int | None = None
    nearest_schools: list[dict] = Field(default_factory=list)
    nearest_transit: list[dict] = Field(default_factory=list)
    transit: dict | None = None


class NegotiationLever(BaseModel):
    title: str
    detail: str
    impact_pct: float | None = None
    strength: Literal["weak", "moderate", "strong"]


class NegotiationScript(BaseModel):
    verdict: str
    levers: list[NegotiationLever]
    opening_message: str


class MarketIndex(BaseModel):
    arrondissement_median_ppm2: float
    listing_vs_median_pct: float


class PhotoAnalysis(BaseModel):
    renovation_state: Literal["raw", "dated", "recent", "premium"]
    view_quality: Literal["courtyard", "street", "panoramic", "unknown"]
    natural_light: Literal["dark", "average", "bright"]


class TransitStop(BaseModel):
    name: str
    line: str
    distance_m: float
    walk_minutes: float


class AnalyzeResponse(BaseModel):
    listing: Listing
    location: GeoLocation | None = None
    valuation: Valuation
    comps: list[Comp]
    building_history: list[Comp] = Field(default_factory=list)
    dpe: DPEReport | None = None
    neighborhood: Neighborhood | None = None
    negotiation: NegotiationScript | None = None
    market_index: MarketIndex | None = None
    photo_analysis: PhotoAnalysis | None = None
    delta_pct: float | None = None
    delta_eur: float | None = None
    warnings: list[str] = Field(default_factory=list)
