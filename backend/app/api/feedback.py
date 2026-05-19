"""POST /analyze/feedback — collect user feedback on estimates.

Persists votes to a DuckDB table so we can identify systematic biases
(e.g. consistently underpricing top-floor units). Lightweight: no auth,
just trace_id + vote + optional free-text.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..db import get_conn

router = APIRouter()
log = logging.getLogger(__name__)

_TABLE_CREATED = False


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, max_length=40)
    vote: Literal["too_low", "fair", "too_high"]
    comment: str | None = Field(None, max_length=1000)


class FeedbackResponse(BaseModel):
    ok: bool = True


def _ensure_table() -> None:
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            trace_id VARCHAR NOT NULL,
            vote VARCHAR NOT NULL,
            comment VARCHAR,
            created_at TIMESTAMP NOT NULL
        );
    """)
    _TABLE_CREATED = True


@router.post("/analyze/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest) -> FeedbackResponse:
    _ensure_table()
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (trace_id, vote, comment, created_at) VALUES (?, ?, ?, ?)",
        [req.trace_id, req.vote, req.comment, datetime.utcnow()],
    )
    log.info("feedback_received trace_id=%s vote=%s", req.trace_id, req.vote)
    return FeedbackResponse()
