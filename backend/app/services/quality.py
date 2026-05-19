"""Runtime quality checks that produce structured warnings.

Each check is a pure function: (listing, location, valuation, comps, dpe_report) → list[Warning].
The analyze endpoint calls `run_all_checks()` after valuation and enriches the response.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from ..models.schemas import Comp, DPEReport, GeoLocation, Listing, Valuation

# Paris price/m² sanity bounds (adjusted for studios → luxury).
PARIS_PPM2_LOW = 4_000
PARIS_PPM2_HIGH = 25_000

# Rooms-to-surface plausibility range (m² per room).
M2_PER_ROOM_LOW = 10
M2_PER_ROOM_HIGH = 45

# Geocode score below which address is "approximate".
GEOCODE_SCORE_THRESHOLD = 0.65


@dataclass
class QualityWarning:
    code: str
    severity: Literal["info", "warning", "error"]
    message_fr: str
    detail: str | None = None


def check_price_per_m2_bounds(listing: Listing) -> list[QualityWarning]:
    """Flag listings with price/m² outside Paris norms."""
    warnings: list[QualityWarning] = []
    if not listing.price_eur or not listing.surface_m2 or listing.surface_m2 <= 0:
        return warnings
    ppm2 = listing.price_eur / listing.surface_m2
    if ppm2 < PARIS_PPM2_LOW:
        warnings.append(QualityWarning(
            code="price_per_m2_low",
            severity="warning",
            message_fr=(
                f"Le prix au m² ({ppm2:,.0f} €/m²) est anormalement bas pour Paris. "
                f"Vérifiez le prix et la surface."
            ),
            detail=f"price_per_m2={ppm2:.0f}, threshold_low={PARIS_PPM2_LOW}",
        ))
    elif ppm2 > PARIS_PPM2_HIGH:
        warnings.append(QualityWarning(
            code="price_per_m2_high",
            severity="warning",
            message_fr=(
                f"Le prix au m² ({ppm2:,.0f} €/m²) est inhabituellement élevé. "
                f"Bien d'exception ou erreur de saisie ?"
            ),
            detail=f"price_per_m2={ppm2:.0f}, threshold_high={PARIS_PPM2_HIGH}",
        ))
    return warnings


def check_surface_rooms_ratio(listing: Listing) -> list[QualityWarning]:
    """Rooms vs. surface plausibility."""
    warnings: list[QualityWarning] = []
    if not listing.rooms or not listing.surface_m2 or listing.rooms <= 0:
        return warnings
    m2_per_room = listing.surface_m2 / listing.rooms
    if m2_per_room < M2_PER_ROOM_LOW:
        warnings.append(QualityWarning(
            code="surface_rooms_low",
            severity="info",
            message_fr=(
                f"Ratio surface/pièces bas ({m2_per_room:.0f} m²/pièce). "
                f"Surface ou nombre de pièces à vérifier."
            ),
            detail=f"m2_per_room={m2_per_room:.1f}",
        ))
    elif m2_per_room > M2_PER_ROOM_HIGH:
        warnings.append(QualityWarning(
            code="surface_rooms_high",
            severity="info",
            message_fr=(
                f"Ratio surface/pièces élevé ({m2_per_room:.0f} m²/pièce). "
                f"Grand appartement ou nombre de pièces sous-déclaré ?"
            ),
            detail=f"m2_per_room={m2_per_room:.1f}",
        ))
    return warnings


def check_geocode_quality(location: GeoLocation | None) -> list[QualityWarning]:
    """Warn when BAN geocode score is low → address approximate."""
    warnings: list[QualityWarning] = []
    if location is None:
        warnings.append(QualityWarning(
            code="geocode_failed",
            severity="error",
            message_fr="Adresse non géolocalisable. L'estimation repose sur le code postal seul.",
        ))
        return warnings
    if location.score is not None and location.score < GEOCODE_SCORE_THRESHOLD:
        warnings.append(QualityWarning(
            code="geocode_low_score",
            severity="warning",
            message_fr=(
                f"Géolocalisation approximative (score {location.score:.2f}). "
                f"Les comparables pourraient ne pas correspondre au bon emplacement."
            ),
            detail=f"ban_score={location.score:.3f}, threshold={GEOCODE_SCORE_THRESHOLD}",
        ))
    if not location.id_parcelle:
        warnings.append(QualityWarning(
            code="no_parcelle",
            severity="info",
            message_fr=(
                "Parcelle cadastrale non identifiée. "
                "L'historique de l'immeuble n'est pas disponible."
            ),
        ))
    return warnings


def check_comps_quality(
    comps: list[Comp],
    valuation: Valuation,
    listing: Listing,
) -> list[QualityWarning]:
    """Warn on thin comparables, old data, or high dispersion."""
    warnings: list[QualityWarning] = []

    if valuation.n_comps == 0:
        warnings.append(QualityWarning(
            code="no_comps",
            severity="error",
            message_fr="Aucun comparable trouvé. L'estimation n'est pas fiable.",
        ))
        return warnings

    if valuation.n_comps < 5:
        warnings.append(QualityWarning(
            code="few_comps",
            severity="warning",
            message_fr=(
                f"Seulement {valuation.n_comps} ventes comparables trouvées. "
                f"L'estimation est indicative."
            ),
            detail=f"n_comps={valuation.n_comps}, tier={valuation.base_tier}",
        ))

    if valuation.base_tier == "iris" and valuation.n_comps < 10:
        warnings.append(QualityWarning(
            code="weak_tier",
            severity="warning",
            message_fr=(
                "Les comparables proviennent du quartier élargi (rayon 500m), "
                "pas de l'immeuble ou de la rue. Précision réduite."
            ),
        ))

    # Check recency: warn if median comp is old
    if comps:
        dates = [c.date_mutation for c in comps if c.date_mutation]
        if dates:
            median_date = sorted(dates)[len(dates) // 2]
            months_old = (date.today() - median_date).days / 30
            if months_old > 12:
                warnings.append(QualityWarning(
                    code="comps_old",
                    severity="warning",
                    message_fr=(
                        f"Les ventes comparables datent en médiane de {months_old:.0f} mois. "
                        f"Le marché a pu évoluer depuis."
                    ),
                    detail=f"median_comp_date={median_date}, months_old={months_old:.1f}",
                ))

    # High dispersion in price/m²
    ppms = [c.price_per_m2 for c in comps if c.price_per_m2 and c.price_per_m2 > 1000]
    if len(ppms) > 2:
        med = statistics.median(ppms)
        if med > 0:
            cv = statistics.stdev(ppms) / med
            if cv > 0.25:
                warnings.append(QualityWarning(
                    code="high_dispersion",
                    severity="info",
                    message_fr=(
                        f"Les prix au m² des comparables varient beaucoup "
                        f"(coefficient de variation : {cv:.0%}). "
                        f"Le quartier est hétérogène."
                    ),
                    detail=f"cv={cv:.3f}, median_ppm2={med:.0f}",
                ))

    return warnings


def check_estimate_vs_comps_outlier(
    listing: Listing,
    valuation: Valuation,
) -> list[QualityWarning]:
    """Flag when the listing price diverges strongly from our estimate."""
    warnings: list[QualityWarning] = []
    if not listing.price_eur or not valuation.fair_value_eur or valuation.fair_value_eur <= 0:
        return warnings
    delta_pct = (listing.price_eur - valuation.fair_value_eur) / valuation.fair_value_eur
    if delta_pct > 0.30:
        warnings.append(QualityWarning(
            code="price_above_estimate",
            severity="warning",
            message_fr=(
                f"Le prix demandé est {delta_pct:.0%} au-dessus de notre estimation. "
                f"Marge de négociation probable, ou bien d'exception non capté par les comparables."
            ),
        ))
    elif delta_pct < -0.25:
        warnings.append(QualityWarning(
            code="price_below_estimate",
            severity="info",
            message_fr=(
                f"Le prix demandé est {abs(delta_pct):.0%} en dessous de notre estimation. "
                f"Bonne affaire potentielle, ou données manquantes (travaux, occupation, etc.)."
            ),
        ))
    return warnings


def check_dpe_mismatch(
    listing: Listing,
    dpe_report: DPEReport | None,
) -> list[QualityWarning]:
    """Cross-check listing DPE vs. official ADEME DPE record."""
    warnings: list[QualityWarning] = []
    if not listing.dpe_class or not dpe_report or not dpe_report.dpe_class:
        return warnings
    listing_dpe = listing.dpe_class.upper()
    ademe_dpe = dpe_report.dpe_class.upper()
    if listing_dpe != ademe_dpe:
        diff = abs(ord(listing_dpe) - ord(ademe_dpe))
        if diff >= 2:
            sev = "warning"
        else:
            sev = "info"
        warnings.append(QualityWarning(
            code="dpe_mismatch",
            severity=sev,
            message_fr=(
                f"DPE de l'annonce ({listing_dpe}) ≠ DPE ADEME ({ademe_dpe}). "
                f"Le DPE a peut-être été refait récemment, ou l'annonce est inexacte."
            ),
            detail=f"listing_dpe={listing_dpe}, ademe_dpe={ademe_dpe}",
        ))
    return warnings


def check_surface_mismatch(
    listing: Listing,
    dpe_report: DPEReport | None,
) -> list[QualityWarning]:
    """Cross-check surface from listing vs. DPE record."""
    warnings: list[QualityWarning] = []
    if not listing.surface_m2 or not dpe_report or not dpe_report.surface_m2:
        return warnings
    diff_pct = abs(listing.surface_m2 - dpe_report.surface_m2) / listing.surface_m2
    if diff_pct > 0.15:
        warnings.append(QualityWarning(
            code="surface_mismatch",
            severity="warning",
            message_fr=(
                f"Surface annonce ({listing.surface_m2:.0f} m²) ≠ surface DPE "
                f"({dpe_report.surface_m2:.0f} m²). Écart de {diff_pct:.0%}."
            ),
            detail=f"listing={listing.surface_m2}, dpe={dpe_report.surface_m2}, diff={diff_pct:.2%}",
        ))
    return warnings


def run_all_checks(
    listing: Listing,
    location: GeoLocation | None,
    valuation: Valuation,
    comps: list[Comp],
    dpe_report: DPEReport | None,
) -> list[QualityWarning]:
    """Run every check, return combined sorted warnings."""
    all_warnings: list[QualityWarning] = []
    all_warnings.extend(check_price_per_m2_bounds(listing))
    all_warnings.extend(check_surface_rooms_ratio(listing))
    all_warnings.extend(check_geocode_quality(location))
    all_warnings.extend(check_comps_quality(comps, valuation, listing))
    all_warnings.extend(check_estimate_vs_comps_outlier(listing, valuation))
    all_warnings.extend(check_dpe_mismatch(listing, dpe_report))
    all_warnings.extend(check_surface_mismatch(listing, dpe_report))

    severity_order = {"error": 0, "warning": 1, "info": 2}
    all_warnings.sort(key=lambda w: severity_order.get(w.severity, 9))
    return all_warnings
