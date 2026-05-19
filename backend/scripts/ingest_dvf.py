"""Bulk-ingest Paris DVF (Demandes de Valeurs Foncières, géolocalisé) into DuckDB.

Source: https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/
Etalab publishes one CSV per year (gzip'd) covering all communes. We pull a
configurable range of years, filter to Paris (department 75 / commune codes
75101..75120), and insert into a single 'mutations' table.

Usage (from backend/):
    uv run python scripts/ingest_dvf.py
    uv run python scripts/ingest_dvf.py --years 2020 2021 2022 2023 2024 2025

The bulk file URL pattern (Etalab CSV/CSV-géolocalisé):
    https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/full.csv.gz
"""
from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import time
from pathlib import Path

import duckdb
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

CSV_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/full.csv.gz"
DEFAULT_YEARS = list(range(2020, 2027))  # 2020–2026 when published on data.gouv.fr

PARIS_COMMUNES = [str(75100 + a) for a in range(1, 21)]  # 75101..75120


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS mutations (
    id_mutation         VARCHAR,
    date_mutation       DATE,
    nature_mutation     VARCHAR,
    valeur_fonciere     DOUBLE,
    adresse_numero      VARCHAR,
    adresse_suffixe     VARCHAR,
    adresse_nom_voie    VARCHAR,
    adresse_code_voie   VARCHAR,
    code_postal         VARCHAR,
    code_commune        VARCHAR,
    nom_commune         VARCHAR,
    code_departement    VARCHAR,
    id_parcelle         VARCHAR,
    nature_culture      VARCHAR,
    type_local          VARCHAR,
    surface_reelle_bati DOUBLE,
    nombre_pieces_principales INTEGER,
    surface_terrain     DOUBLE,
    longitude           DOUBLE,
    latitude            DOUBLE,
    -- derived
    price_per_m2        DOUBLE,
    adresse             VARCHAR,
    PRIMARY KEY (id_mutation, id_parcelle)
);

CREATE INDEX IF NOT EXISTS idx_mutations_parcelle
    ON mutations (id_parcelle);
CREATE INDEX IF NOT EXISTS idx_mutations_voie
    ON mutations (code_postal, adresse_nom_voie);
CREATE INDEX IF NOT EXISTS idx_mutations_date
    ON mutations (date_mutation);
"""


def download(year: int, dest: Path) -> Path:
    """Stream-download the year's full.csv.gz to disk."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"[ok ] cached {dest.name} ({dest.stat().st_size/1e6:.1f}MB)")
        return dest
    url = CSV_URL.format(year=year)
    print(f"[get] {url}")
    with httpx.stream(
        "GET", url, timeout=120.0, follow_redirects=True
    ) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(".part")
        n = 0
        with tmp.open("wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
                n += len(chunk)
        tmp.rename(dest)
        print(f"[ok ] saved {dest.name} ({n/1e6:.1f}MB)")
    return dest


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_DDL)


def load_year(con: duckdb.DuckDBPyConnection, gz_path: Path, year: int) -> int:
    """Load a single year's gz CSV into DuckDB, filtered to Paris communes."""
    paris_list = ",".join(f"'{c}'" for c in PARIS_COMMUNES)
    # DuckDB can read .gz directly via read_csv_auto. We filter on the fly.
    sql = f"""
    INSERT OR IGNORE INTO mutations
    SELECT
        id_mutation,
        CAST(date_mutation AS DATE),
        nature_mutation,
        TRY_CAST(valeur_fonciere AS DOUBLE),
        adresse_numero,
        adresse_suffixe,
        adresse_nom_voie,
        adresse_code_voie,
        code_postal,
        code_commune,
        nom_commune,
        code_departement,
        id_parcelle,
        nature_culture,
        type_local,
        TRY_CAST(surface_reelle_bati AS DOUBLE),
        TRY_CAST(nombre_pieces_principales AS INTEGER),
        TRY_CAST(surface_terrain AS DOUBLE),
        TRY_CAST(longitude AS DOUBLE),
        TRY_CAST(latitude AS DOUBLE),
        CASE
            WHEN TRY_CAST(surface_reelle_bati AS DOUBLE) > 9
                 AND TRY_CAST(valeur_fonciere AS DOUBLE) > 0
            THEN TRY_CAST(valeur_fonciere AS DOUBLE)
                 / TRY_CAST(surface_reelle_bati AS DOUBLE)
            ELSE NULL
        END AS price_per_m2,
        TRIM(
            COALESCE(adresse_numero, '')
            || COALESCE(' ' || adresse_suffixe, '')
            || COALESCE(' ' || adresse_nom_voie, '')
        ) AS adresse
    FROM read_csv_auto(
        '{gz_path}',
        compression='gzip',
        header=true,
        all_varchar=true,
        sample_size=-1
    )
    WHERE code_commune IN ({paris_list})
      AND nature_mutation IN ('Vente', 'Vente en l''état futur d''achèvement')
      AND TRY_CAST(valeur_fonciere AS DOUBLE) IS NOT NULL
      AND TRY_CAST(valeur_fonciere AS DOUBLE) > 10000;
    """
    t0 = time.time()
    cnt_before = con.execute("SELECT COUNT(*) FROM mutations;").fetchone()[0]
    con.execute(sql)
    cnt_after = con.execute("SELECT COUNT(*) FROM mutations;").fetchone()[0]
    inserted = cnt_after - cnt_before
    print(
        f"[ok ] {year}: +{inserted:,} rows in {time.time()-t0:.1f}s "
        f"(total now {cnt_after:,})"
    )
    return inserted


def sanity_check(con: duckdb.DuckDBPyConnection) -> None:
    print("\n=== Sanity check ===")
    n = con.execute("SELECT COUNT(*) FROM mutations;").fetchone()[0]
    print(f"Total Paris transactions: {n:,}")
    rows = con.execute(
        """
        SELECT code_postal, COUNT(*) AS n,
               ROUND(MEDIAN(price_per_m2)) AS median_eur_m2
        FROM mutations
        WHERE type_local = 'Appartement' AND price_per_m2 IS NOT NULL
        GROUP BY code_postal
        ORDER BY code_postal;
        """
    ).fetchall()
    print(f"{'CP':<6} {'n':>8} {'median €/m²':>14}")
    for cp, c, med in rows:
        cp_s = cp or "—"
        med_s = f"{med:,.0f}" if med else "—"
        print(f"{cp_s:<6} {c:>8} {med_s:>14}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    p.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("DVF_CACHE", str(ROOT / "data" / "dvf"))),
    )
    args = p.parse_args()

    cfg = settings()
    cfg.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(cfg.duckdb_path))
    con.execute("INSTALL spatial; LOAD spatial;")
    ensure_schema(con)

    total = 0
    for year in args.years:
        gz_path = args.data_dir / f"dvf-{year}.csv.gz"
        try:
            download(year, gz_path)
        except httpx.HTTPError as e:
            print(f"[err] {year}: download failed ({e}); skipping")
            continue
        try:
            total += load_year(con, gz_path, year)
        except duckdb.Error as e:
            print(f"[err] {year}: load failed ({e}); skipping")

    print(f"\nDone. {total:,} new rows across {len(args.years)} year(s).")
    sanity_check(con)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
