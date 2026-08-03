"""Scale BB / APC generational projection integration module (KDB side).

Module that applies the generational projection (per-issue-year 1D tables)
to the KDB SQLite DB.

Note (2026-07-16): the "assumed rate tables" produced by this module are in
fact rate tables computed from cause-specific mortality (per 100,000
population, derived from mortality_apc_panel). The paper (as retitled on
2026-07-15) uses cause-specific mortality on two levels: (i) as a "proxy" for
medical-insurance disease incidence rates, and (ii) as the "target itself
(direct assumption)" for specified-disease death benefits. The "incidence"
wording is product-facing terminology; inputs and computations are
consistently cause-specific mortality (the algorithm is agnostic to the
meaning of its input).

Purpose:
    Slice ``scalebb_projection`` (3D: sex × age × year) via the generational
    projection and upsert into ``predicted_rate_generational``
    (per-issue-year 1D [age] tables). Downstream systems can thereby use the
    results of this research model while keeping their existing
    ``[sex, age]`` lookup.

Public API::

    build_generational_tables(
        db_path, run_id, issue_years, issue_age, age_min, age_max, ...
    ) -> dict
        Read from ``scalebb_projection`` in the DB → compute → upsert to DB
        + CSV output (for distribution to downstream systems)

Design rationale: see Document/methodology_apc_extension_20260422.md §8A for details.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from .db import PROJECT_ROOT, connect


# ---------------------------------------------------------------------------
# Age interpolation (5-year bin → single year)
# ---------------------------------------------------------------------------
def interpolate_projection_ages(
    proj: pd.DataFrame,
    *,
    age_min: int,
    age_max: int,
    method: Literal["log_linear", "linear", "log_pchip"] = "log_linear",
) -> pd.DataFrame:
    """Interpolate a 5-year-bin (40, 45, 50, ...) ``scalebb_projection`` to single ages.

    mortality_apc_panel comes from e-Stat and is in 5-year age groups.
    Contract-based assumed rate tables require single ages, so we
    interpolate here.

    Since disease incidence rates increase roughly exponentially with age,
    the default is **linear interpolation in log space** (= log-linear in
    age). Outside the boundaries (age < min_known, age > max_known),
    extrapolate flat with the edge values.

    Args:
        proj: columns [disease_id, sex, section, age, year, rate_projected]
        age_min, age_max: output single-age range (inclusive)
        method:
            - 'log_linear' (recommended): linear interpolation of log(rate) in age
            - 'linear'          : linear interpolation of rate in age
            - 'log_pchip'       : monotone PCHIP interpolation of log(rate) (requires scipy)

    Returns:
        A long DataFrame interpolated to single ages. For each original
        `(disease, sex, section, year)` group, age is expanded to the
        contiguous values age_min..age_max.
    """
    required = {"disease_id", "sex", "section", "age", "year", "rate_projected"}
    missing = required - set(proj.columns)
    if missing:
        raise ValueError(f"projection missing columns: {missing}")

    ages_out = np.arange(int(age_min), int(age_max) + 1)
    out_frames: list[pd.DataFrame] = []

    group_keys = ["disease_id", "sex", "section", "year"]
    for grp_key, sub in proj.groupby(group_keys, dropna=False):
        did, sx, sec, yr = grp_key
        sub = sub.dropna(subset=["rate_projected"]).sort_values("age")
        if sub.empty:
            continue
        ages_in = sub["age"].to_numpy(dtype=float)
        rates_in = sub["rate_projected"].to_numpy(dtype=float)

        if len(ages_in) < 2:
            rate_interp = np.full_like(ages_out, fill_value=rates_in[0], dtype=float)
        else:
            rate_interp = _interpolate_rates(
                ages_known=ages_in,
                rates_known=rates_in,
                ages_target=ages_out.astype(float),
                method=method,
            )

        out_frames.append(
            pd.DataFrame(
                {
                    "disease_id": did,
                    "sex": sx,
                    "section": sec,
                    "age": ages_out.astype(int),
                    "year": int(yr),
                    "rate_projected": rate_interp,
                }
            )
        )
    if not out_frames:
        return pd.DataFrame(
            columns=[
                "disease_id",
                "sex",
                "section",
                "age",
                "year",
                "rate_projected",
            ]
        )
    return pd.concat(out_frames, ignore_index=True)


def _interpolate_rates(
    *,
    ages_known: np.ndarray,
    rates_known: np.ndarray,
    ages_target: np.ndarray,
    method: str,
) -> np.ndarray:
    """Single-age interpolation engine (internal)."""
    ages_known = np.asarray(ages_known, dtype=float)
    rates_known = np.asarray(rates_known, dtype=float)

    if method in ("log_linear", "log_pchip"):
        pos_mask = rates_known > 0
        if pos_mask.sum() < 2:
            return np.interp(ages_target, ages_known, rates_known)
        x = ages_known[pos_mask]
        y = np.log(rates_known[pos_mask])
        if method == "log_pchip":
            try:
                from scipy.interpolate import PchipInterpolator

                f = PchipInterpolator(x, y, extrapolate=True)
                log_interp = f(ages_target)
            except Exception:
                log_interp = np.interp(ages_target, x, y)
        else:
            log_interp = np.interp(ages_target, x, y)
        return np.exp(log_interp)
    return np.interp(ages_target, ages_known, rates_known)


def build_generational_tables(
    *,
    db_path: str | Path,
    run_id: str,
    issue_years: Iterable[int],
    issue_age: int,
    age_min: int,
    age_max: int,
    disease_ids: Iterable[str] | None = None,
    sexes: Iterable[str] | None = None,
    section: str = "total",
    output_dir: str | Path | None = None,
    load_to_db: bool = True,
    interpolate_age: bool = False,
    interpolation_method: Literal["log_linear", "linear", "log_pchip"] = "log_linear",
) -> dict:
    """Build per-issue-year 1D tables from the Scale BB projection and write to DB/CSV.

    Args:
        db_path: SQLite DB path
        run_id: run_id of the target ``scalebb_projection``
        issue_years: list of issue years (e.g. [2024, 2025, 2026])
        issue_age: age at issue (0 = track aging from newborn, 40 = product issued at age 40, etc.)
        age_min, age_max: lower/upper bounds of the reference ages (inclusive)
        disease_ids: target diseases (defaults to all diseases in run_id)
        sexes: target sexes (defaults to all sexes contained in run_id)
        section: 'total' / 'inpatient' / 'outpatient'
        output_dir: CSV output directory (defaults to <repo>/data/processed/predicted_rate_tables)
        load_to_db: if True, load into predicted_rate_generational

    Returns:
        {'run_id', 'rows_loaded', 'files_written', 'output_dir', 'master_csv'}
    """
    conn = connect(db_path)
    try:
        proj = _fetch_projection(
            conn,
            run_id=run_id,
            disease_ids=disease_ids,
            sexes=sexes,
            section=section,
        )
    finally:
        conn.close()

    if proj.empty:
        raise ValueError(
            f"no matching rows found in scalebb_projection (run_id={run_id})"
        )

    # 5-year bin → single-age interpolation (contract assumed rates require single ages)
    if interpolate_age:
        before_n = len(proj)
        proj = interpolate_projection_ages(
            proj,
            age_min=age_min,
            age_max=age_max,
            method=interpolation_method,
        )
        print(
            f"[interpolate] method={interpolation_method} "
            f"rows: {before_n} → {len(proj)}"
        )

    issue_years = sorted({int(y) for y in issue_years})
    out_dir = _resolve_output_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    files_written: list[Path] = []
    for y0 in issue_years:
        tbl = _build_cohort_table_from_df(
            proj,
            issue_year=y0,
            issue_age=issue_age,
            age_min=age_min,
            age_max=age_max,
            section=section,
        )
        frames.append(tbl)
        for path in _write_compat_csvs(tbl, out_dir, issue_year=y0, issue_age=issue_age):
            files_written.append(path)

    master = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    master_csv = out_dir / f"predicted_rate_master_{run_id[:8]}.csv"
    master.to_csv(master_csv, index=False, encoding="utf-8-sig")

    rows_loaded = 0
    if load_to_db and not master.empty:
        master["run_id"] = run_id
        rows_loaded = load_generational_to_db(db_path, master, run_id=run_id)

    return {
        "run_id": run_id,
        "rows_loaded": rows_loaded,
        "files_written": [str(p) for p in files_written],
        "output_dir": str(out_dir),
        "master_csv": str(master_csv),
    }


def load_generational_to_db(
    db_path: str | Path,
    df: pd.DataFrame,
    *,
    run_id: str,
) -> int:
    """Upsert into ``predicted_rate_generational``.

    Args:
        df: DataFrame with columns [run_id, disease_id, sex, issue_year,
             issue_age, age, rate_per_100k, year_lookup]
        run_id: run_id to replace (existing rows for the same run_id are deleted before INSERT)
    """
    required = {
        "run_id",
        "disease_id",
        "sex",
        "issue_year",
        "issue_age",
        "age",
        "rate_per_100k",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"generational table missing columns: {missing}")

    df_out = df.copy()
    if "section" not in df_out.columns:
        df_out["section"] = "total"
    if "year_lookup" not in df_out.columns:
        df_out["year_lookup"] = None

    cols = [
        "run_id",
        "disease_id",
        "sex",
        "section",
        "issue_year",
        "issue_age",
        "age",
        "rate_per_100k",
        "year_lookup",
    ]
    df_out = df_out[cols]

    conn = connect(db_path)
    try:
        conn.execute(
            "DELETE FROM predicted_rate_generational WHERE run_id = ?", (run_id,)
        )
        _bulk_insert(conn, "predicted_rate_generational", df_out)
        conn.commit()
    finally:
        conn.close()
    return len(df_out)


def fetch_generational(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    disease_id: str | Iterable[str] | None = None,
    sex: str | None = None,
    issue_year: int | Iterable[int] | None = None,
    issue_age: int | None = None,
) -> pd.DataFrame:
    """Filtered query against ``predicted_rate_generational``."""
    where: list[str] = ["1 = 1"]
    params: list = []
    if run_id:
        where.append("run_id = ?")
        params.append(run_id)
    if disease_id is not None:
        if isinstance(disease_id, str):
            where.append("disease_id = ?")
            params.append(disease_id)
        else:
            ids = list(disease_id)
            where.append(f"disease_id IN ({','.join(['?'] * len(ids))})")
            params.extend(ids)
    if sex:
        where.append("sex = ?")
        params.append(sex)
    if issue_year is not None:
        if isinstance(issue_year, int):
            where.append("issue_year = ?")
            params.append(int(issue_year))
        else:
            ys = list(issue_year)
            where.append(f"issue_year IN ({','.join(['?'] * len(ys))})")
            params.extend([int(y) for y in ys])
    if issue_age is not None:
        where.append("issue_age = ?")
        params.append(int(issue_age))

    sql = (
        "SELECT * FROM predicted_rate_generational "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY disease_id, sex, issue_year, issue_age, age"
    )
    return pd.read_sql_query(sql, conn, params=params)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _resolve_output_dir(output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        p = Path(output_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    # KDB/data/processed/predicted_rate_tables
    return PROJECT_ROOT / "data" / "processed" / "predicted_rate_tables"


def _fetch_projection(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    disease_ids: Iterable[str] | None,
    sexes: Iterable[str] | None,
    section: str,
) -> pd.DataFrame:
    where = ["run_id = ?"]
    params: list = [run_id]
    if disease_ids:
        ids = list(disease_ids)
        where.append(f"disease_id IN ({','.join(['?'] * len(ids))})")
        params.extend(ids)
    if sexes:
        sxs = list(sexes)
        where.append(f"sex IN ({','.join(['?'] * len(sxs))})")
        params.extend(sxs)
    if section:
        where.append("section = ?")
        params.append(section)
    sql = (
        "SELECT disease_id, sex, section, age, year, rate_projected "
        "FROM scalebb_projection "
        f"WHERE {' AND '.join(where)}"
    )
    return pd.read_sql_query(sql, conn, params=params)


def _build_cohort_table_from_df(
    proj: pd.DataFrame,
    *,
    issue_year: int,
    issue_age: int,
    age_min: int,
    age_max: int,
    section: str,
) -> pd.DataFrame:
    """Build the 1D [age] table for a single (issue_year, issue_age)."""
    frames = []
    for (disease, sex), sub in proj.groupby(["disease_id", "sex"]):
        ages = np.arange(age_min, age_max + 1)
        rows = []
        for x in ages:
            if x < issue_age:
                rows.append(
                    {
                        "age": int(x),
                        "rate_per_100k": None,
                        "year_lookup": None,
                    }
                )
                continue
            y_target = issue_year + (int(x) - issue_age)
            cell = sub[(sub["age"] == int(x)) & (sub["year"] == int(y_target))]
            rate = None
            if not cell.empty:
                val = float(cell["rate_projected"].iloc[0])
                if np.isfinite(val):
                    rate = val
            rows.append(
                {
                    "age": int(x),
                    "rate_per_100k": rate,
                    "year_lookup": int(y_target),
                }
            )
        tbl = pd.DataFrame(rows)
        tbl.insert(0, "disease_id", disease)
        tbl.insert(1, "sex", sex)
        tbl.insert(2, "section", section)
        tbl.insert(3, "issue_year", issue_year)
        tbl.insert(4, "issue_age", issue_age)
        frames.append(tbl)
    if not frames:
        return pd.DataFrame(
            columns=[
                "disease_id",
                "sex",
                "section",
                "issue_year",
                "issue_age",
                "age",
                "rate_per_100k",
                "year_lookup",
            ]
        )
    return pd.concat(frames, ignore_index=True)


def _write_compat_csvs(
    tbl: pd.DataFrame,
    out_dir: Path,
    *,
    issue_year: int,
    issue_age: int,
) -> list[Path]:
    """Write downstream-compatible 2-column ``age, rate_per_100k`` CSVs per disease × sex."""
    saved: list[Path] = []
    if tbl.empty:
        return saved
    for (disease, sex), sub in tbl.groupby(["disease_id", "sex"]):
        pivot = (
            sub.set_index("age")["rate_per_100k"].sort_index().to_frame()
        )
        fname = (
            f"predicted_rate_{disease}_{sex}_issue{issue_year}_ia{issue_age}.csv"
        )
        path = out_dir / fname
        pivot.to_csv(path, encoding="utf-8-sig")
        saved.append(path)
    return saved


def _bulk_insert(
    conn: sqlite3.Connection, table: str, df: pd.DataFrame
) -> None:
    cols = df.columns.tolist()
    col_list = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    def _cell(v: object) -> object:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        return v

    rows = [tuple(_cell(v) for v in row) for row in df.itertuples(index=False)]
    conn.executemany(sql, rows)


__all__ = [
    "build_generational_tables",
    "interpolate_projection_ages",
    "load_generational_to_db",
    "fetch_generational",
]
