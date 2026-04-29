# backend

FastAPI service for the Paris Buyer Copilot.

```bash
uv sync
cp .env.example .env
uv run python scripts/ingest_dvf.py --years 2022 2023 2024 2025
uv run uvicorn app.main:app --reload --port 8000
```

OpenAPI: <http://localhost:8000/docs>

## Endpoints

- `POST /analyze` — `{"url": "..."}` → full bundle (listing, comps, valuation, DPE, neighborhood, negotiation).
- `GET /health` — backend status + DVF row count.

## Tests

```bash
uv run pytest -q
```

`tests/test_dvf_query.py` and `tests/test_analyze_endpoint.py` are
auto-skipped when `data/paris.duckdb` is absent (i.e. before ingest).
