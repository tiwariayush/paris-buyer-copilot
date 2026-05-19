"""Backtest valuation accuracy against held-out DVF sales.

For each sale in the test window, we reconstruct what the copilot would have
estimated *before* that sale happened (excluding the sale itself and any
future sales from the comp pool). Then we compare predicted fair value vs.
actual transaction price.

Usage:
    uv run python scripts/backtest.py
    uv run python scripts/backtest.py --test-months 6 --sample 500 --output reports/backtest.md
"""
from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.schemas import Comp, Listing, Valuation
from app.services.valuation import value_listing

cfg = settings()


@dataclass
class BacktestResult:
    id_mutation: str
    date_mutation: date
    actual_price: float
    actual_surface: float
    actual_ppm2: float
    code_postal: str
    estimated_fair_value: float | None
    estimated_ppm2: float | None
    confidence: str
    n_comps: int
    base_tier: str
    abs_error_eur: float | None = None
    abs_error_pct: float | None = None
    in_band: bool | None = None


@dataclass
class BacktestReport:
    test_window_start: date
    test_window_end: date
    total_tested: int = 0
    total_with_estimate: int = 0
    total_skipped: int = 0
    results: list[BacktestResult] = field(default_factory=list)

    # Aggregate metrics
    mae_eur: float = 0.0
    mae_pct: float = 0.0
    median_abs_error_pct: float = 0.0
    band_coverage_pct: float = 0.0

    # By confidence
    by_confidence: dict[str, dict] = field(default_factory=dict)
    # By arrondissement
    by_arrondissement: dict[str, dict] = field(default_factory=dict)
    # By tier
    by_tier: dict[str, dict] = field(default_factory=dict)


PARIS_PPM2_FLOOR = 4000
BASE_COLS = """
    id_mutation, date_mutation, valeur_fonciere, surface_reelle_bati,
    nombre_pieces_principales, type_local, adresse, code_postal,
    id_parcelle, longitude, latitude, price_per_m2
"""


def _get_test_sales(
    conn: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    sample_size: int,
) -> list[dict]:
    """Get apartment sales in the test window, with required fields."""
    sql = f"""
        SELECT {BASE_COLS}
        FROM mutations
        WHERE date_mutation BETWEEN ? AND ?
          AND type_local = 'Appartement'
          AND surface_reelle_bati > 8
          AND surface_reelle_bati < 300
          AND price_per_m2 >= {PARIS_PPM2_FLOOR}
          AND price_per_m2 <= 25000
          AND longitude IS NOT NULL
          AND latitude IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """
    rows = conn.execute(sql, [start, end, sample_size]).fetchall()
    cols = [
        "id_mutation", "date_mutation", "valeur_fonciere", "surface_reelle_bati",
        "nombre_pieces_principales", "type_local", "adresse", "code_postal",
        "id_parcelle", "longitude", "latitude", "price_per_m2",
    ]
    return [dict(zip(cols, row)) for row in rows]


def _get_comps_before(
    conn: duckdb.DuckDBPyConnection,
    sale: dict,
    months_back: int = 18,
) -> tuple[list[Comp], str]:
    """Find comps for this sale using only transactions BEFORE it."""
    sale_date = sale["date_mutation"]
    cutoff = sale_date - timedelta(days=months_back * 30)
    lon, lat = sale["longitude"], sale["latitude"]
    surface = sale["surface_reelle_bati"]
    id_parcelle = sale["id_parcelle"]
    code_postal = sale["code_postal"]

    smin = surface * 0.7
    smax = surface * 1.3

    def _cos_deg(deg: float) -> float:
        return math.cos(math.radians(deg))

    radius_m = 500
    deg_lat = radius_m / 111_000
    deg_lon = radius_m / (111_000 * max(0.1, abs(_cos_deg(lat))))

    # Tier 1: building
    building_comps = []
    if id_parcelle:
        sql = f"""
            SELECT {BASE_COLS}
            FROM mutations
            WHERE id_parcelle = ?
              AND date_mutation >= ? AND date_mutation < ?
              AND type_local = 'Appartement'
              AND price_per_m2 >= {PARIS_PPM2_FLOOR}
              AND id_mutation != ?
            ORDER BY date_mutation DESC
            LIMIT 50
        """
        rows = conn.execute(sql, [id_parcelle, cutoff, sale_date, sale["id_mutation"]]).fetchall()
        building_comps = [_row_to_comp(r, "building") for r in rows]
        if len(building_comps) >= 3:
            return building_comps, "building"

    # Tier 2: radius (acts as IRIS substitute)
    sql = f"""
        WITH base AS (
            SELECT {BASE_COLS},
                   ST_Distance_Sphere(
                       ST_Point(longitude, latitude),
                       ST_Point(?, ?)
                   ) AS distance_m
            FROM mutations
            WHERE longitude IS NOT NULL AND latitude IS NOT NULL
              AND date_mutation >= ? AND date_mutation < ?
              AND type_local = 'Appartement'
              AND surface_reelle_bati BETWEEN ? AND ?
              AND price_per_m2 >= {PARIS_PPM2_FLOOR}
              AND ABS(latitude - ?) < ?
              AND ABS(longitude - ?) < ?
              AND id_mutation != ?
        )
        SELECT * FROM base
        WHERE distance_m <= ?
        ORDER BY distance_m ASC
        LIMIT 60
    """
    rows = conn.execute(sql, [
        lon, lat,
        cutoff, sale_date,
        smin, smax,
        lat, deg_lat,
        lon, deg_lon,
        sale["id_mutation"],
        radius_m,
    ]).fetchall()
    radius_comps = [_row_to_comp(r[:-1], "iris") for r in rows]

    combined = building_comps + radius_comps
    if combined:
        tier = "building" if len(building_comps) >= 3 else "iris"
        return combined, tier
    return [], "none"


def _row_to_comp(r: tuple, tier: str) -> Comp:
    return Comp(
        id_mutation=r[0],
        date_mutation=r[1],
        valeur_fonciere=r[2],
        surface_reelle_bati=r[3],
        nombre_pieces_principales=r[4],
        type_local=r[5],
        adresse=r[6],
        code_postal=r[7],
        id_parcelle=r[8],
        longitude=r[9],
        latitude=r[10],
        price_per_m2=r[11],
        tier=tier,
    )


def _compute_group_metrics(results: list[BacktestResult]) -> dict:
    """Compute aggregate metrics for a group of results."""
    with_estimate = [r for r in results if r.estimated_fair_value is not None]
    if not with_estimate:
        return {"n": len(results), "n_estimated": 0}

    abs_errors_pct = [r.abs_error_pct for r in with_estimate if r.abs_error_pct is not None]
    abs_errors_eur = [r.abs_error_eur for r in with_estimate if r.abs_error_eur is not None]
    in_band = [r.in_band for r in with_estimate if r.in_band is not None]

    return {
        "n": len(results),
        "n_estimated": len(with_estimate),
        "mae_pct": statistics.mean(abs_errors_pct) if abs_errors_pct else 0,
        "median_abs_error_pct": statistics.median(abs_errors_pct) if abs_errors_pct else 0,
        "mae_eur": statistics.mean(abs_errors_eur) if abs_errors_eur else 0,
        "band_coverage_pct": (sum(in_band) / len(in_band) * 100) if in_band else 0,
    }


def run_backtest(
    test_months: int = 6,
    sample_size: int = 500,
) -> BacktestReport:
    """Run the backtest and return a structured report."""
    conn = duckdb.connect(str(cfg.duckdb_path), read_only=True)
    conn.execute("LOAD spatial;")

    end = date.today()
    start = end - timedelta(days=test_months * 30)

    report = BacktestReport(test_window_start=start, test_window_end=end)

    print(f"Fetching test sales from {start} to {end} (sample={sample_size})...")
    test_sales = _get_test_sales(conn, start, end, sample_size)
    print(f"  → {len(test_sales)} test sales loaded")

    for i, sale in enumerate(test_sales):
        if (i + 1) % 50 == 0:
            print(f"  Processing {i+1}/{len(test_sales)}...")

        comps, tier = _get_comps_before(conn, sale)

        listing = Listing(
            source_url="https://backtest.local/",
            portal="backtest",
            price_eur=sale["valeur_fonciere"],
            surface_m2=sale["surface_reelle_bati"],
            rooms=sale["nombre_pieces_principales"],
            address_raw=sale["adresse"],
            postal_code=sale["code_postal"],
        )

        val = value_listing(listing, comps, tier)

        result = BacktestResult(
            id_mutation=sale["id_mutation"],
            date_mutation=sale["date_mutation"],
            actual_price=sale["valeur_fonciere"],
            actual_surface=sale["surface_reelle_bati"],
            actual_ppm2=sale["price_per_m2"],
            code_postal=sale["code_postal"],
            estimated_fair_value=val.fair_value_eur,
            estimated_ppm2=val.price_per_m2_estimate,
            confidence=val.confidence,
            n_comps=val.n_comps,
            base_tier=val.base_tier,
        )

        if val.fair_value_eur and val.fair_value_eur > 0:
            error_eur = abs(sale["valeur_fonciere"] - val.fair_value_eur)
            result.abs_error_eur = error_eur
            result.abs_error_pct = error_eur / sale["valeur_fonciere"] * 100

            if val.fair_value_low_eur and val.fair_value_high_eur:
                result.in_band = (
                    val.fair_value_low_eur <= sale["valeur_fonciere"] <= val.fair_value_high_eur
                )

        report.results.append(result)

    conn.close()

    # Compute aggregates
    with_estimate = [r for r in report.results if r.estimated_fair_value is not None]
    report.total_tested = len(report.results)
    report.total_with_estimate = len(with_estimate)
    report.total_skipped = report.total_tested - report.total_with_estimate

    all_metrics = _compute_group_metrics(report.results)
    report.mae_eur = all_metrics.get("mae_eur", 0)
    report.mae_pct = all_metrics.get("mae_pct", 0)
    report.median_abs_error_pct = all_metrics.get("median_abs_error_pct", 0)
    report.band_coverage_pct = all_metrics.get("band_coverage_pct", 0)

    # By confidence
    by_conf: dict[str, list] = defaultdict(list)
    for r in report.results:
        by_conf[r.confidence].append(r)
    report.by_confidence = {k: _compute_group_metrics(v) for k, v in by_conf.items()}

    # By arrondissement (code_postal → 75001..75020)
    by_arr: dict[str, list] = defaultdict(list)
    for r in report.results:
        by_arr[r.code_postal].append(r)
    report.by_arrondissement = {k: _compute_group_metrics(v) for k, v in sorted(by_arr.items())}

    # By tier
    by_tier: dict[str, list] = defaultdict(list)
    for r in report.results:
        by_tier[r.base_tier].append(r)
    report.by_tier = {k: _compute_group_metrics(v) for k, v in by_tier.items()}

    return report


def format_report(report: BacktestReport) -> str:
    """Format the report as a markdown document."""
    lines: list[str] = []
    lines.append("# Backtest Report")
    lines.append(f"\n**Test window:** {report.test_window_start} → {report.test_window_end}")
    lines.append(f"**Sales tested:** {report.total_tested}")
    lines.append(f"**With estimate:** {report.total_with_estimate}")
    lines.append(f"**Skipped (no comps):** {report.total_skipped}")

    lines.append("\n## Overall Accuracy")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Mean Absolute Error (€) | {report.mae_eur:,.0f} € |")
    lines.append(f"| Mean Absolute Error (%) | {report.mae_pct:.1f}% |")
    lines.append(f"| Median Absolute Error (%) | {report.median_abs_error_pct:.1f}% |")
    lines.append(f"| Band coverage (actual in [low, high]) | {report.band_coverage_pct:.1f}% |")

    lines.append("\n## By Confidence Level")
    lines.append("| Confidence | N | MAE % | Median AE % | Band Coverage |")
    lines.append("|------------|---|-------|-------------|---------------|")
    for conf in ["high", "medium", "low"]:
        m = report.by_confidence.get(conf, {})
        if not m or m.get("n", 0) == 0:
            continue
        lines.append(
            f"| {conf} | {m['n']} | {m.get('mae_pct', 0):.1f}% | "
            f"{m.get('median_abs_error_pct', 0):.1f}% | {m.get('band_coverage_pct', 0):.1f}% |"
        )

    lines.append("\n## By Comp Tier")
    lines.append("| Tier | N | MAE % | Median AE % | Band Coverage |")
    lines.append("|------|---|-------|-------------|---------------|")
    for tier in ["building", "street", "iris", "none"]:
        m = report.by_tier.get(tier, {})
        if not m or m.get("n", 0) == 0:
            continue
        lines.append(
            f"| {tier} | {m['n']} | {m.get('mae_pct', 0):.1f}% | "
            f"{m.get('median_abs_error_pct', 0):.1f}% | {m.get('band_coverage_pct', 0):.1f}% |"
        )

    lines.append("\n## By Arrondissement")
    lines.append("| Code Postal | N | MAE % | Median AE % | Band Coverage |")
    lines.append("|-------------|---|-------|-------------|---------------|")
    for cp, m in report.by_arrondissement.items():
        if m.get("n", 0) == 0:
            continue
        lines.append(
            f"| {cp} | {m['n']} | {m.get('mae_pct', 0):.1f}% | "
            f"{m.get('median_abs_error_pct', 0):.1f}% | {m.get('band_coverage_pct', 0):.1f}% |"
        )

    # Worst predictions (biggest % errors)
    worst = sorted(
        [r for r in report.results if r.abs_error_pct is not None],
        key=lambda r: r.abs_error_pct or 0,
        reverse=True,
    )[:10]
    if worst:
        lines.append("\n## Worst 10 Predictions")
        lines.append("| Mutation | Date | Actual | Estimated | Error % | Tier | Comps |")
        lines.append("|----------|------|--------|-----------|---------|------|-------|")
        for r in worst:
            lines.append(
                f"| {r.id_mutation[:12]}… | {r.date_mutation} | "
                f"{r.actual_price:,.0f} € | {r.estimated_fair_value:,.0f} € | "
                f"{r.abs_error_pct:.1f}% | {r.base_tier} | {r.n_comps} |"
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Backtest valuation accuracy")
    parser.add_argument("--test-months", type=int, default=6, help="Months in test window")
    parser.add_argument("--sample", type=int, default=500, help="Max sales to test")
    parser.add_argument("--output", type=str, default=None, help="Output markdown file")
    args = parser.parse_args()

    t0 = time.time()
    report = run_backtest(test_months=args.test_months, sample_size=args.sample)
    elapsed = time.time() - t0

    md = format_report(report)
    print(md)
    print(f"\n---\nBacktest completed in {elapsed:.1f}s")

    output_path = args.output
    if not output_path:
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        output_path = str(reports_dir / f"backtest-{date.today()}.md")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(md, encoding="utf-8")
    print(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()
