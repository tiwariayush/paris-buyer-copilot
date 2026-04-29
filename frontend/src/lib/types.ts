// Mirrors backend/app/models/schemas.py
export type Tier = "building" | "street" | "iris" | "none";
export type Confidence = "low" | "medium" | "high";
export type Strength = "weak" | "moderate" | "strong";

export interface Listing {
  source_url: string;
  portal: string;
  title?: string | null;
  price_eur?: number | null;
  surface_m2?: number | null;
  rooms?: number | null;
  bedrooms?: number | null;
  address_raw?: string | null;
  postal_code?: string | null;
  city?: string | null;
  description?: string | null;
  photos: string[];
  dpe_class?: string | null;
  floor?: number | null;
  has_elevator?: boolean | null;
}

export interface GeoLocation {
  lat: number;
  lon: number;
  address_normalized: string;
  score?: number | null;
  id_parcelle?: string | null;
  code_iris?: string | null;
  nom_iris?: string | null;
  code_commune: string;
  code_postal?: string | null;
}

export interface Comp {
  id_mutation: string;
  date_mutation: string;
  valeur_fonciere: number;
  surface_reelle_bati?: number | null;
  nombre_pieces_principales?: number | null;
  type_local?: string | null;
  adresse?: string | null;
  code_postal?: string | null;
  id_parcelle?: string | null;
  longitude?: number | null;
  latitude?: number | null;
  price_per_m2?: number | null;
  tier: Tier;
  distance_m?: number | null;
}

export interface DPEReport {
  dpe_class?: string | null;
  ges_class?: string | null;
  consumption_kwh_m2_year?: number | null;
  emissions_kgco2_m2_year?: number | null;
  surface_m2?: number | null;
  year_certified?: number | null;
  address?: string | null;
}

export interface Valuation {
  fair_value_eur: number | null;
  fair_value_low_eur: number | null;
  fair_value_high_eur: number | null;
  price_per_m2_estimate: number | null;
  confidence: Confidence;
  n_comps: number;
  base_tier: Tier;
  adjustments: Record<string, number>;
  rationale: string;
}

export interface Neighborhood {
  iris_code?: string | null;
  iris_name?: string | null;
  median_household_income_eur?: number | null;
  population?: number | null;
  nearest_schools: Array<{
    name?: string;
    type?: string;
    nature?: string;
    city?: string;
    lat?: number;
    lon?: number;
  }>;
  transit?: Record<string, unknown> | null;
}

export interface NegotiationLever {
  title: string;
  detail: string;
  impact_pct?: number | null;
  strength: Strength;
}

export interface NegotiationScript {
  verdict: string;
  levers: NegotiationLever[];
  opening_message: string;
}

export interface AnalyzeResponse {
  listing: Listing;
  location?: GeoLocation | null;
  valuation: Valuation;
  comps: Comp[];
  dpe?: DPEReport | null;
  neighborhood?: Neighborhood | null;
  negotiation?: NegotiationScript | null;
  delta_pct?: number | null;
  delta_eur?: number | null;
  warnings: string[];
}
