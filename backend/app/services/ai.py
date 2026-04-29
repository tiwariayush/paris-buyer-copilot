"""LLM-powered verdict + negotiation script.

Given the structured analysis bundle, produce:
- a one-paragraph verdict (factual, citing comps),
- 3 ranked negotiation levers with concrete impact,
- a short opening message the buyer can send to the agent.

We use OpenAI's structured outputs so the result is type-safe.
Falls back to a deterministic rule-based script when no API key is set.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..models.schemas import (
    Comp,
    DPEReport,
    Listing,
    NegotiationLever,
    NegotiationScript,
    Valuation,
)


SYSTEM_PROMPT = """\
You are a senior buyer-side real-estate analyst in Paris. Speak French \
when producing customer-facing copy (verdict, opening_message), but keep \
internal labels English. Be concise, factual, and never invent comparables.\
Cite at most 2 specific comparables by date+address+price."""


def _fallback(
    listing: Listing,
    valuation: Valuation,
    delta_pct: float | None,
    dpe: DPEReport | None,
    comps: list[Comp],
) -> NegotiationScript:
    levers: list[NegotiationLever] = []
    if delta_pct is not None and delta_pct > 0:
        fv = int(round(valuation.fair_value_eur or 0))
        levers.append(
            NegotiationLever(
                title=f"Surévalué de {delta_pct:.0f}%",
                detail=(
                    f"L'estimation médiane sur {valuation.n_comps} biens "
                    f"comparables ({valuation.base_tier}) "
                    f"ressort à environ {fv:,} €.".replace(",", "\u00a0")
                ),
                impact_pct=-delta_pct,
                strength="strong" if delta_pct > 7 else "moderate",
            )
        )
    if dpe and dpe.dpe_class in {"F", "G"}:
        levers.append(
            NegotiationLever(
                title=f"DPE {dpe.dpe_class} – passoire thermique",
                detail=(
                    "Travaux énergétiques obligatoires (interdiction de "
                    "louer en G dès 2025, F dès 2028)."
                ),
                impact_pct=-8 if dpe.dpe_class == "F" else -12,
                strength="strong",
            )
        )
    if listing.has_elevator is False and (listing.floor or 0) >= 4:
        levers.append(
            NegotiationLever(
                title=f"{listing.floor}e étage sans ascenseur",
                detail="Frein notable à la liquidité, à intégrer au prix.",
                impact_pct=-5,
                strength="moderate",
            )
        )
    if not levers:
        levers.append(
            NegotiationLever(
                title="Aligné avec le marché",
                detail=(
                    "Le prix demandé est cohérent avec les transactions récentes."
                ),
                strength="weak",
            )
        )
    verdict_bits = []
    if delta_pct is not None:
        verdict_bits.append(
            f"Prix demandé {abs(delta_pct):.0f}% "
            f"{'au-dessus' if delta_pct > 0 else 'en dessous'} du marché."
        )
    if comps:
        c0 = comps[0]
        prix = f"{int(c0.valeur_fonciere):,}".replace(",", "\u00a0")
        verdict_bits.append(
            f"Dernière vente comparable : {c0.adresse or '?'} "
            f"({c0.date_mutation}) à {prix} €."
        )
    verdict = " ".join(verdict_bits) or "Données insuffisantes pour conclure."

    if valuation.fair_value_eur:
        fv = f"{int(round(valuation.fair_value_eur)):,}".replace(",", "\u00a0")
        opening = (
            "Bonjour, je suis intéressé(e) par ce bien. Au regard des "
            "transactions récentes du quartier et des éléments du dossier, "
            f"je serais en mesure de me positionner autour de {fv} €. "
            "Pouvons-nous en discuter ?"
        )
    else:
        opening = (
            "Bonjour, je suis intéressé(e) par ce bien. Pouvons-nous échanger "
            "sur le prix au regard des dernières ventes du quartier ?"
        )
    return NegotiationScript(verdict=verdict, levers=levers, opening_message=opening)


def _build_context(
    listing: Listing,
    valuation: Valuation,
    delta_pct: float | None,
    delta_eur: float | None,
    dpe: DPEReport | None,
    comps: list[Comp],
) -> str:
    return json.dumps(
        {
            "listing": listing.model_dump(mode="json"),
            "valuation": valuation.model_dump(mode="json"),
            "delta_pct": delta_pct,
            "delta_eur": delta_eur,
            "dpe": dpe.model_dump(mode="json") if dpe else None,
            "comparables": [c.model_dump(mode="json") for c in comps[:8]],
        },
        ensure_ascii=False,
        default=str,
    )


async def negotiate(
    listing: Listing,
    valuation: Valuation,
    comps: list[Comp],
    delta_pct: float | None,
    delta_eur: float | None,
    dpe: DPEReport | None,
) -> NegotiationScript:
    cfg = settings()
    if not cfg.openai_api_key:
        return _fallback(listing, valuation, delta_pct, dpe, comps)
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return _fallback(listing, valuation, delta_pct, dpe, comps)

    client = AsyncOpenAI(api_key=cfg.openai_api_key)
    context = _build_context(listing, valuation, delta_pct, delta_eur, dpe, comps)

    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string"},
            "opening_message": {"type": "string"},
            "levers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "impact_pct": {"type": ["number", "null"]},
                        "strength": {
                            "type": "string",
                            "enum": ["weak", "moderate", "strong"],
                        },
                    },
                    "required": ["title", "detail", "impact_pct", "strength"],
                },
            },
        },
        "required": ["verdict", "opening_message", "levers"],
    }

    try:
        resp = await client.chat.completions.create(
            model=cfg.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Analyse ce dossier et produis un verdict, 3 leviers "
                        "de négociation classés par force, et un message "
                        "d'ouverture en français. Données :\n\n" + context
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "negotiation",
                    "schema": schema,
                    "strict": True,
                },
            },
            temperature=0.3,
        )
        payload = json.loads(resp.choices[0].message.content or "{}")
        return NegotiationScript(**payload)
    except Exception:
        return _fallback(listing, valuation, delta_pct, dpe, comps)
