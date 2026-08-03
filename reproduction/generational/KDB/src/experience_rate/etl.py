"""CSV → SQLite ETL (ingestion) processing.

This module is dedicated to bulk-loading the population-based disease
incidence panel (``incidence_panel.csv`` / ``rider_disease_map.csv``).

Since this reproduction environment does not handle policy data
(in-force and movement records), the ingestion features for
experience rate (A/E) analysis are not bundled.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from .db import PROJECT_ROOT, connect

# Load order for population-based disease incidence (incidence_panel, rider_disease_map).
INCIDENCE_LOAD_ORDER: list[tuple[str, str]] = [
    ("population_incidence", "incidence_panel.csv"),
    ("rider_disease_map", "rider_disease_map.csv"),
]


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def load_incidence_panel(
    db_path: str | Path,
    data_dir: str | Path,
    *,
    verbose: bool = True,
) -> dict[str, int]:
    """Load the population-based incidence panel (incidence_panel.csv etc.) into the DB.

    Args:
        db_path: SQLite file
        data_dir: Directory to search for CSVs (usually ``data/processed``)
    """
    data_dir_path = _resolve(data_dir)
    if not data_dir_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir_path}")

    conn = connect(db_path)
    counts: dict[str, int] = {}
    try:
        for table, csv_name in INCIDENCE_LOAD_ORDER:
            csv_path = data_dir_path / csv_name
            if not csv_path.exists():
                if verbose:
                    print(f"  [skip] {table}: {csv_path.name} does not exist")
                counts[table] = 0
                continue

            # Before loading rider_disease_map, auto-fill rider_code into rider_def
            # (rider_def is a display master with no FK constraint, but keep it
            #  populated so that rider_name lookups work for analyze results)
            if table == "rider_disease_map":
                added = _upsert_rider_def_from_map(conn, csv_path)
                if verbose and added:
                    print(f"  [auto] rider_def: filled in {added} rider_code entries")

            n = _load_incidence_csv_to_table(conn, table, csv_path)
            counts[table] = n
            if verbose:
                print(f"  [load] {table}: {n} rows (from {csv_path.name})")
        conn.commit()
    finally:
        conn.close()
    return counts


def _upsert_rider_def_from_map(conn: sqlite3.Connection, csv_path: Path) -> int:
    """Upsert ``rider_code`` values from ``rider_disease_map.csv`` into ``rider_def``.

    Existing rows are not overwritten; only unregistered rider_code values
    are inserted with minimal information.
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    if df.empty or "rider_code" not in df.columns:
        return 0

    codes = sorted({str(c).strip() for c in df["rider_code"].dropna().tolist() if str(c).strip()})
    if not codes:
        return 0

    existing = {
        row[0]
        for row in conn.execute("SELECT rider_code FROM rider_def").fetchall()
    }
    missing = [c for c in codes if c not in existing]
    if not missing:
        return 0

    conn.executemany(
        "INSERT INTO rider_def (rider_code, rider_name, rider_category, display_order) "
        "VALUES (?, ?, ?, ?)",
        [(c, c, "auto_generated", i) for i, c in enumerate(missing)],
    )
    return len(missing)


def _load_incidence_csv_to_table(
    conn: sqlite3.Connection,
    table: str,
    csv_path: Path,
) -> int:
    """Load incidence_panel.csv → population_incidence with column mapping.

    The column names in incidence_panel.csv basically match those of
    population_incidence, but sex is stored as a string
    ('total'/'male'/'female'), so the sex_code column replaces sex.
    """
    df = pd.read_csv(
        csv_path, encoding="utf-8-sig", keep_default_na=False, na_values=[""]
    )

    if df.empty:
        return 0

    if table == "population_incidence":
        if "sex_code" in df.columns:
            df["sex"] = (
                pd.to_numeric(df["sex_code"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        elif "sex" in df.columns and df["sex"].dtype == object:
            mapping = {"total": 0, "male": 1, "female": 2}
            df["sex"] = df["sex"].map(mapping).fillna(0).astype(int)

        pk_cols = ["disease_norm", "sex", "age_code", "year", "section", "rate_type"]
        pk_cols = [c for c in pk_cols if c in df.columns]
        df = df.dropna(subset=pk_cols)

        keep = [
            "disease_id",
            "disease_norm",
            "icd10",
            "sex",
            "age_code",
            "age_low",
            "age_high",
            "year",
            "section",
            "rate_type",
            "incidence_rate_annual",
            "incidence_rate_per_100k",
            "numerator_count",
            "population_thousand",
            "source_table",
            "quality_flag",
            "method_note",
        ]
        df = df[[c for c in keep if c in df.columns]]

        for c in ("sex", "age_low", "age_high", "year"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        for c in (
            "incidence_rate_annual",
            "incidence_rate_per_100k",
            "numerator_count",
            "population_thousand",
        ):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    conn.execute(f"DELETE FROM {table}")
    cols = df.columns.tolist()
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(f'"{c}"' for c in cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    def _cell(v):
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        return v

    rows = [tuple(_cell(v) for v in row) for row in df.itertuples(index=False)]
    conn.executemany(sql, rows)
    return len(rows)


def show_summary(db_path: str | Path, tables: Iterable[str] | None = None) -> None:
    """Show row counts for each table."""
    conn = connect(db_path)
    try:
        if tables is None:
            tables = [
                "parameters",
                "rider_def",
                "rider_disease_map",
                "population_incidence",
            ]
        print("Table summary:")
        for t in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<22} {n:>8} rows")
            except sqlite3.OperationalError:
                print(f"  {t:<22}        - (not exists)")

        # Scale BB tables are optional (silently skip if they do not exist)
        for t in (
            "scalebb_run",
            "scalebb_improvement",
            "scalebb_cohort_effect",
            "scalebb_projection",
            "predicted_rate_generational",
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<22} {n:>8} rows")
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()


def build_population_benchmark(
    conn: sqlite3.Connection,
    *,
    disease_ids: list[str] | None = None,
    rate_types: list[str] | None = None,
    year: int | None = None,
    sex: int | None = None,
) -> pd.DataFrame:
    """Fetch population benchmark incidence rates from population_incidence.

    Args:
        disease_ids: disease_id values to filter on (e.g. ['cancer', 'heart_disease'])
        rate_types:  rate_type values to filter on (e.g. ['registry', 'initial_visit'])
        year:        filter by year
        sex:         filter by 0=total/1=male/2=female

    Returns:
        DataFrame of the population_incidence table (filtered by the given conditions)
    """
    clauses: list[str] = []
    params: list = []
    if disease_ids:
        placeholders = ",".join(["?"] * len(disease_ids))
        clauses.append(f"disease_id IN ({placeholders})")
        params.extend(disease_ids)
    if rate_types:
        placeholders = ",".join(["?"] * len(rate_types))
        clauses.append(f"rate_type IN ({placeholders})")
        params.extend(rate_types)
    if year is not None:
        clauses.append("year = ?")
        params.append(year)
    if sex is not None:
        clauses.append("sex = ?")
        params.append(sex)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            disease_id, disease_norm, icd10, sex, age_code, age_low, age_high,
            year, section, rate_type,
            incidence_rate_annual, incidence_rate_per_100k,
            numerator_count, population_thousand,
            source_table, quality_flag, method_note
        FROM population_incidence
        {where}
        ORDER BY disease_id, rate_type, year, sex, age_low
    """
    return pd.read_sql_query(sql, conn, params=tuple(params))
