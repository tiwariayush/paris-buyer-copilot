# Paris Buyer Copilot

Buyer-side AI copilot for Paris real estate. Paste any listing URL
(Bien'ici, SeLoger, LeBonCoin, PAP) and get, in seconds:

- Fair-value estimate with comparables drawn from DVF (every notarized
  sale in France since 2014).
- Same-building transaction history when available.
- Energy class (DPE) and renovation-cost lever for F/G properties.
- Schools + neighborhood context.
- A short negotiation script tailored to the listing.

The wedge: information asymmetry is the only thing keeping buy-side
real-estate commissions at 2.5–3%. France already publishes the
underlying data (DVF, DPE, BAN, IRIS, IDFM) under Etalab 2.0 — we just
surface it where buyers actually need it.

## Stack

- **Backend:** FastAPI + DuckDB (spatial) + httpx, managed by `uv`.
- **Frontend:** Next.js 16 (App Router) + Tailwind v4 + MapLibre.
- **Data:**
  - DVF géolocalisé ([data.gouv.fr](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/)) — every Paris transaction.
  - API DPE Logements ([data.ademe.fr](https://data.ademe.fr/datasets/dpe-v2-logements-existants)) — energy class.
  - BAN ([adresse.data.gouv.fr](https://adresse.data.gouv.fr/)) — geocoding.
  - IGN api-carto cadastre — parcel ID for same-building joins.
  - data.education.gouv.fr — schools.

## Quick start

```bash
# 1. Backend — Python 3.12 via uv
cd backend
uv sync
cp .env.example .env   # fill OPENAI_API_KEY (optional; falls back to a deterministic script)

# 2. Ingest DVF Paris (one-shot, ~5 min for 2022–2025)
uv run python scripts/ingest_dvf.py --years 2022 2023 2024 2025

# 3. Run API
uv run uvicorn app.main:app --reload --port 8000

# 4. Frontend — Node 20+
cd ../frontend
pnpm install
pnpm dev   # http://localhost:3000
```

## End-to-end smoke test (fixture)

With the API running:

```bash
cd backend
uv run python scripts/demo.py
```

Spawns a tiny localhost server with a fixture listing (5 rue du Faubourg
du Temple, 75011) and pipes it through `/analyze`. Should print a JSON
response with ~9 street-tier comparables, a DPE class, and a French
negotiation script.

## Project layout

```
backend/
  app/
    api/        FastAPI routers (/analyze, /health)
    services/   listing_parser, geocoder, dvf, dpe, neighborhood, valuation, ai, cache
    models/     Pydantic schemas (becomes the OpenAPI surface)
    db.py       DuckDB connection helper
    config.py   .env-driven settings
  scripts/
    ingest_dvf.py   bulk DVF Paris loader
    demo.py         end-to-end smoke test with fixture HTML
  tests/        pytest

frontend/
  src/app/      Next.js routes (/, /verdict)
  src/components/  PriceCard, ComparablesMap, BuildingHistory, DPECard, NeighborhoodCard, NegotiationScript
  src/lib/      api client + types mirror of backend schemas
```

## Legal posture

DVF, DPE, BAN, IRIS are all Etalab 2.0 — commercial reuse is fine with
attribution. Listing pages are fetched **one URL at a time, on user
request**, and we read only the public JSON-LD that portals already
publish for SEO. We never bulk-crawl, never store full listing photos
or descriptions, and never use the data outside the user's own session.

## Roadmap (not in v1)

- Listing tracking (re-fetch user-pasted listings; log price drops).
- ML AVM trained on click-through telemetry.
- IDFM transit isochrone ("door-to-door to La Défense").
- Co-ownership red flags (registre-coproprietes.gouv.fr).
- iOS/Android share extension (paste from native browser share sheet).
