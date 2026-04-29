"""Health + DB stats endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..services.dvf import stats

router = APIRouter()


@router.get("/health")
def health() -> dict:
    try:
        s = stats()
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
    return {"status": "ok", "dvf": s}
