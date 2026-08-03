"""KDB-side integration module for the Scale BB extended model.

Calls the KDB-bundled ``_scalebb_core`` package (``model`` / ``apc_model`` /
``panels`` / ``disease`` / ``heatmap``) directly in-process, and loads the
fit / projection results into the KDB SQLite DB so they can be queried
just like ``analyze_benchmark``.

Public API::

    run_fit(db_path, source, **kwargs) -> dict
    run_projection(db_path, fit_file, **kwargs) -> dict
    run_heatmap(output_dir, source, **kwargs) -> list[Path]
    load_fit_to_db(db_path, fit_csv | parquet, meta_json) -> int
    load_projection_to_db(db_path, projection_csv | parquet, meta_json) -> int
    list_runs(conn) -> pd.DataFrame
    fetch_improvement(conn, run_id, ...) -> pd.DataFrame
    fetch_projection(conn, run_id, ...) -> pd.DataFrame

Write targets are ``scalebb_run`` / ``scalebb_improvement`` / ``scalebb_projection``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ._scalebb_core import disease as _disease
from ._scalebb_core import heatmap as _heatmap
from .db import PROJECT_ROOT, connect


# ---------------------------------------------------------------------------
# run_fit / run_projection: call _scalebb_core in-process + load into DB
# ---------------------------------------------------------------------------
def run_fit(
    *,
    db_path: str | Path,
    source: str = "mortality",
    diseases: Iterable[str] | None = None,
    sex: str = "total",
    section: str = "total",
    age_min: int = 20,
    age_max: int = 89,
    year_min: int | None = None,
    year_max: int | None = None,
    lam_row: float = 40.0,
    lam_col: float = 40.0,
    output_path: str | Path | None = None,
    run_id: str | None = None,
    load_to_db: bool = True,
) -> dict[str, Any]:
    """Run the Scale BB Phase 1 fit and write results to CSV/parquet + DB.

    Returns:
        dict: {'run_id', 'output_file', 'rows_loaded'}
    """
    if output_path is None:
        output_path = PROJECT_ROOT / "data" / "processed" / "scalebb_fit.parquet"
    output_path = Path(output_path).resolve()

    result = _disease.run_fit_to_file(
        output=output_path,
        source=source,
        diseases=diseases,
        sex=sex,
        section=section,
        age_min=age_min,
        age_max=age_max,
        year_min=year_min,
        year_max=year_max,
        lam_row=lam_row,
        lam_col=lam_col,
        run_id=run_id,
    )

    rows = 0
    meta_path = Path(result["meta_file"])
    if load_to_db and output_path.exists():
        rows = load_fit_to_db(
            db_path, output_path, meta_json_path=meta_path, source_panel=source
        )
    return {
        "run_id": result["run_id"],
        "output_file": str(output_path),
        "rows_loaded": rows,
    }


def run_projection(
    *,
    db_path: str | Path,
    fit_file: str | Path,
    long_term_rate: float = 0.01,
    convergence_year: int = 2035,
    horizon: int = 2050,
    last_observed_year: int | None = None,
    output_path: str | Path | None = None,
    run_id: str | None = None,
    load_to_db: bool = True,
) -> dict[str, Any]:
    """Run the Scale BB Phase 2 projection and load it into the DB."""
    fit_file = Path(fit_file).resolve()
    if not fit_file.exists():
        raise FileNotFoundError(f"fit file not found: {fit_file}")
    if output_path is None:
        output_path = PROJECT_ROOT / "data" / "processed" / "scalebb_projection.parquet"
    output_path = Path(output_path).resolve()

    result = _disease.run_project_to_file(
        fit_file=fit_file,
        output=output_path,
        long_term_rate=long_term_rate,
        convergence_year=convergence_year,
        horizon_year=horizon,
        last_observed_year=last_observed_year,
        run_id=run_id,
    )

    rows = 0
    meta_path = Path(result["meta_file"])
    if load_to_db and output_path.exists():
        rows = load_projection_to_db(
            db_path,
            output_path,
            meta_json_path=meta_path,
            source_panel="projection",
        )
    return {
        "run_id": result["run_id"],
        "output_file": str(output_path),
        "rows_loaded": rows,
    }


def run_heatmap(
    *,
    output_dir: str | Path,
    source: str = "mortality",
    diseases: Iterable[str] | None = None,
    sex: str = "total",
    section: str = "total",
    age_min: int = 20,
    age_max: int = 89,
    year_min: int | None = None,
    year_max: int | None = None,
    long_term_rate: float = 0.01,
    convergence_year: int = 2035,
    horizon: int = 2050,
) -> list[Path]:
    """Generate heatmap / projection line-chart PNGs and return the saved paths."""
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    argv: list[str] = [
        "--source", source,
        "--sex", sex,
        "--section", section,
        "--age-min", str(age_min),
        "--age-max", str(age_max),
        "--long-term-rate", str(long_term_rate),
        "--convergence-year", str(convergence_year),
        "--horizon", str(horizon),
        "--output-dir", str(output_dir),
    ]
    if source == "mortality" and diseases:
        argv.extend(["--disease", *diseases])
    if year_min is not None:
        argv.extend(["--year-min", str(year_min)])
    if year_max is not None:
        argv.extend(["--year-max", str(year_max)])

    print(f"[scalebb] heatmap argv = {' '.join(argv)}")
    before = set(output_dir.glob("*.png"))
    rc = _heatmap.main(argv)
    if rc != 0:
        raise RuntimeError(f"scalebb heatmap failed (rc={rc})")
    after = set(output_dir.glob("*.png"))
    return sorted(after - before) or sorted(after)


# ---------------------------------------------------------------------------
# DB load: fit CSV / projection CSV → SQLite
# ---------------------------------------------------------------------------
def load_fit_to_db(
    db_path: str | Path,
    fit_file: str | Path,
    *,
    meta_json_path: str | Path | None = None,
    source_panel: str | None = None,
) -> int:
    """Load a Phase 1 fit result CSV/parquet into ``scalebb_improvement``."""
    path = Path(fit_file)
    df = _read_frame(path)
    if df.empty:
        return 0

    required = {
        "run_id",
        "source_stream",
        "disease_id",
        "sex",
        "section",
        "age",
        "year",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"fit file missing columns: {missing}")

    meta = _read_meta(meta_json_path)
    run_id = str(df["run_id"].iloc[0])

    conn = connect(db_path)
    try:
        _upsert_run_row(
            conn,
            run_id=run_id,
            kind="fit",
            df=df,
            meta=meta,
            source_panel=source_panel,
            source_file=str(path),
        )

        cols = [
            "run_id",
            "source_stream",
            "disease_id",
            "sex",
            "section",
            "age",
            "year",
            "rate_observed",
            "rate_smoothed",
            "improvement_observed",
            "improvement_smoothed",
        ]
        df_out = df.copy()
        for c in cols:
            if c not in df_out.columns:
                df_out[c] = None
        df_out = df_out[cols]

        conn.execute("DELETE FROM scalebb_improvement WHERE run_id = ?", (run_id,))
        _bulk_insert(conn, "scalebb_improvement", df_out)
        conn.commit()
    finally:
        conn.close()
    print(f"[scalebb] loaded {len(df)} rows into scalebb_improvement (run_id={run_id})")
    return len(df)


def load_projection_to_db(
    db_path: str | Path,
    projection_file: str | Path,
    *,
    meta_json_path: str | Path | None = None,
    source_panel: str | None = None,
) -> int:
    """Load a Phase 2 projection result into ``scalebb_projection``."""
    path = Path(projection_file)
    df = _read_frame(path)
    if df.empty:
        return 0
    required = {
        "run_id",
        "source_stream",
        "disease_id",
        "sex",
        "section",
        "age",
        "year",
        "is_observed",
        "improvement_final",
        "rate_projected",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"projection file missing columns: {missing}")

    meta = _read_meta(meta_json_path)
    run_id = str(df["run_id"].iloc[0])

    conn = connect(db_path)
    try:
        _upsert_run_row(
            conn,
            run_id=run_id,
            kind="projection",
            df=df,
            meta=meta,
            source_panel=source_panel,
            source_file=str(path),
        )
        cols = [
            "run_id",
            "source_stream",
            "disease_id",
            "sex",
            "section",
            "age",
            "year",
            "is_observed",
            "improvement_final",
            "rate_projected",
        ]
        df_out = df.copy()
        df_out["is_observed"] = (
            df_out["is_observed"].astype(bool).astype(int)
        )
        df_out = df_out[cols]
        conn.execute("DELETE FROM scalebb_projection WHERE run_id = ?", (run_id,))
        _bulk_insert(conn, "scalebb_projection", df_out)
        conn.commit()
    finally:
        conn.close()
    print(
        f"[scalebb] loaded {len(df)} rows into scalebb_projection "
        f"(run_id={run_id})"
    )
    return len(df)


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------
def list_runs(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return the ``scalebb_run`` listing as a DataFrame (newest first)."""
    try:
        return pd.read_sql_query(
            "SELECT * FROM scalebb_run ORDER BY created_at DESC",
            conn,
        )
    except Exception:
        return pd.DataFrame()


def fetch_improvement(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    disease_id: str | Iterable[str] | None = None,
    sex: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    sql, params = _build_filter_sql(
        "scalebb_improvement",
        run_id=run_id,
        disease_id=disease_id,
        sex=sex,
        age_min=age_min,
        age_max=age_max,
        year_min=year_min,
        year_max=year_max,
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return pd.read_sql_query(sql, conn, params=params)


def fetch_projection(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    disease_id: str | Iterable[str] | None = None,
    sex: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    only_projection: bool = False,
    limit: int | None = None,
) -> pd.DataFrame:
    sql, params = _build_filter_sql(
        "scalebb_projection",
        run_id=run_id,
        disease_id=disease_id,
        sex=sex,
        age_min=age_min,
        age_max=age_max,
        year_min=year_min,
        year_max=year_max,
    )
    if only_projection:
        sql += " AND is_observed = 0"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return pd.read_sql_query(sql, conn, params=params)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, encoding="utf-8-sig")


def _read_meta(meta_path: str | Path | None) -> dict:
    if meta_path is None:
        return {}
    p = Path(meta_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_run_id(meta_path: str | Path | None) -> str | None:
    meta = _read_meta(meta_path)
    return meta.get("run_id")


def _extract_run_metadata(df: pd.DataFrame, meta: dict) -> dict:
    """Extract attributes for the scalebb_run row from the DataFrame + meta.json."""
    def _col_stat(col: str, fn):
        if col in df.columns and not df[col].empty:
            try:
                return fn(df[col])
            except Exception:
                return None
        return None

    diseases = (
        ",".join(sorted(df["disease_id"].dropna().astype(str).unique()))
        if "disease_id" in df.columns
        else None
    )
    sex = df["sex"].iloc[0] if "sex" in df.columns and len(df) else None
    section = df["section"].iloc[0] if "section" in df.columns and len(df) else None

    cfg: dict = {}
    entries = meta.get("entries") if isinstance(meta, dict) else None
    if entries:
        cfg_entry = entries[0].get("config", {}) if isinstance(entries[0], dict) else {}
        cfg = cfg_entry
    elif isinstance(meta, dict) and "config" in meta:
        cfg = meta["config"]

    return {
        "diseases": diseases,
        "sex": sex,
        "section": section,
        "age_min": int(_col_stat("age", lambda s: s.min())) if _col_stat("age", lambda s: s.min()) is not None else None,
        "age_max": int(_col_stat("age", lambda s: s.max())) if _col_stat("age", lambda s: s.max()) is not None else None,
        "year_min": int(_col_stat("year", lambda s: s.min())) if _col_stat("year", lambda s: s.min()) is not None else None,
        "year_max": int(_col_stat("year", lambda s: s.max())) if _col_stat("year", lambda s: s.max()) is not None else None,
        "long_term_rate": cfg.get("long_term_rate"),
        "convergence_year": cfg.get("convergence_year"),
        "horizon_year": cfg.get("horizon_year"),
        "lam_row": cfg.get("lam_row"),
        "lam_col": cfg.get("lam_col"),
        "config_json": json.dumps(cfg, ensure_ascii=False) if cfg else None,
    }


def _upsert_run_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    kind: str,
    df: pd.DataFrame,
    meta: dict,
    source_panel: str | None,
    source_file: str | None,
) -> None:
    meta_cols = _extract_run_metadata(df, meta)
    conn.execute(
        """
        INSERT OR REPLACE INTO scalebb_run (
            run_id, kind, source_panel, diseases, sex, section,
            age_min, age_max, year_min, year_max,
            long_term_rate, convergence_year, horizon_year,
            lam_row, lam_col, config_json, source_file, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  COALESCE((SELECT created_at FROM scalebb_run WHERE run_id = ?),
                           datetime('now')))
        """,
        (
            run_id,
            kind,
            source_panel,
            meta_cols["diseases"],
            meta_cols["sex"],
            meta_cols["section"],
            meta_cols["age_min"],
            meta_cols["age_max"],
            meta_cols["year_min"],
            meta_cols["year_max"],
            meta_cols["long_term_rate"],
            meta_cols["convergence_year"],
            meta_cols["horizon_year"],
            meta_cols["lam_row"],
            meta_cols["lam_col"],
            meta_cols["config_json"],
            source_file,
            None,
            run_id,
        ),
    )


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


def _build_filter_sql(
    table: str,
    *,
    run_id: str | None,
    disease_id: str | Iterable[str] | None,
    sex: str | None,
    age_min: int | None,
    age_max: int | None,
    year_min: int | None,
    year_max: int | None,
) -> tuple[str, list]:
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
    if age_min is not None:
        where.append("age >= ?")
        params.append(int(age_min))
    if age_max is not None:
        where.append("age <= ?")
        params.append(int(age_max))
    if year_min is not None:
        where.append("year >= ?")
        params.append(int(year_min))
    if year_max is not None:
        where.append("year <= ?")
        params.append(int(year_max))

    sql = f"SELECT * FROM {table} WHERE {' AND '.join(where)} ORDER BY disease_id, sex, age, year"
    return sql, params


__all__ = [
    "run_fit",
    "run_projection",
    "run_heatmap",
    "load_fit_to_db",
    "load_projection_to_db",
    "list_runs",
    "fetch_improvement",
    "fetch_projection",
]
