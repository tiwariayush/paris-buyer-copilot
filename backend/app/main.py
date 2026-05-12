"""FastAPI entry point for the Paris Buyer Copilot backend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analyze, health
from .config import settings
from .logging_setup import configure_app_logging

configure_app_logging()

app = FastAPI(
    title="Paris Buyer Copilot",
    description=(
        "Buyer-side AI copilot for Paris real estate. Paste a listing URL, "
        "get fair value, comparables, DPE, neighborhood context and a "
        "negotiation script — built on free open data (DVF, DPE, BAN, IRIS)."
    ),
    version="0.1.0",
)

cfg = settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)

app.include_router(health.router, tags=["meta"])
app.include_router(analyze.router, tags=["analyze"])
