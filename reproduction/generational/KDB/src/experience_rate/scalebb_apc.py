"""KDB integration module for the Scale BB APC (Age-Period-Cohort) extension.

Calls the KDB-bundled ``_scalebb_core.apc_model`` (``fit_scale_bb_apc`` /
``project_scale_bb_apc``) directly, and stores γ(c) in the
``scalebb_cohort_effect`` table in addition to the SQLite DB tables
``scalebb_run`` / ``scalebb_improvement`` / ``scalebb_projection``.

Public API::

    run_apc_fit(db_path, source, **kwargs) -> dict
    run_apc_project(db_path, fit_file, **kwargs) -> dict
    load_apc_fit_to_db(...)     # scalebb_improvement + scalebb_cohort_effect
    load_apc_projection_to_db(...)  # scalebb_projection (+ γ extrapolation)

Design policy:
    - Phase 1 fit / Phase 2 project are **completed within a single Python call**.
      The APC-specific γ(c) can be written to the DB directly from the return
      value of ``fit_scale_bb_apc``.
    - Since tables are shared with the existing AP version (``scalebb.py``),
      APC-specific information is stored separately in
      ``scalebb_run.config_json`` and ``scalebb_cohort_effect``.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from ._scalebb_core.apc_model import (
    ScaleBBAPCConfig,
    fit_scale_bb_apc,
    project_scale_bb_apc,
)
from ._scalebb_core.model import (
    ScaleBBConfig,
    ScaleBBFitResult,
    build_blended_improvements,
    project_rates,
)
from ._scalebb_core.panels import (
    load_age_period_matrix,
    load_mortality_matrix,
)
from .db import PROJECT_ROOT, connect


# ---------------------------------------------------------------------------
# High-level fit
# ---------------------------------------------------------------------------
def run_apc_fit(
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
    lam_cohort: float = 40.0,
    long_term_rate: float = 0.01,
    convergence_year: int = 2035,
    horizon_year: int = 2100,
    covid_years: Iterable[int] = (2020, 2021, 2022),
    covid_weight: float = 0.3,
    covid_mode: Literal["weight_down", "dummy", "none"] = "dummy",
    output_path: str | Path | None = None,
    run_id: str | None = None,
    load_to_db: bool = True,
) -> dict[str, Any]:
    """Run the Scale BB APC Phase 1 fit and save to parquet/CSV + DB.

    Returns:
        {'run_id', 'output_file', 'rows_loaded', 'cohorts_loaded', 'fits'}
    """
    run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%S") + "_apc"
    if output_path is None:
        output_path = PROJECT_ROOT / "data" / "processed" / f"scalebb_apc_fit_{sex}.parquet"
    output_path = Path(output_path).resolve()

    cfg = ScaleBBAPCConfig(
        lam_row=lam_row,
        lam_col=lam_col,
        lam_cohort=lam_cohort,
        long_term_rate=long_term_rate,
        convergence_year=convergence_year,
        horizon_year=horizon_year,
        covid_years=tuple(int(y) for y in covid_years),
        covid_weight=float(covid_weight),
        covid_mode=covid_mode,
    )

    matrices = _load_matrices(
        source=source,
        diseases=diseases,
        sex=sex,
        section=section,
        age_min=age_min,
        age_max=age_max,
        year_min=year_min,
        year_max=year_max,
    )
    if not matrices:
        raise RuntimeError("no observation matrices available for the APC fit")

    fit_rows: list[pd.DataFrame] = []
    cohort_rows: list[pd.DataFrame] = []
    fits: dict[str, Any] = {}

    for did, (ages, years, rates) in matrices.items():
        print(
            f"[apc-fit] disease={did} sex={sex} section={section} "
            f"n_age={len(ages)} n_year={len(years)} "
            f"year_range={int(years.min())}-{int(years.max())} "
            f"covid_mode={covid_mode}"
        )
        fit = fit_scale_bb_apc(rates, ages=ages, years=years, config=cfg)
        fits[did] = fit

        fit_rows.append(
            _fit_to_long(
                fit,
                disease_id=did,
                sex=sex,
                section=section,
                source_stream=f"{source}_apc/{did}",
                run_id=run_id,
            )
        )
        cohort_rows.append(
            _cohort_to_long(
                fit,
                disease_id=did,
                sex=sex,
                section=section,
                run_id=run_id,
            )
        )

    fit_df = pd.concat(fit_rows, ignore_index=True)
    cohort_df = pd.concat(cohort_rows, ignore_index=True)

    _save_frame(fit_df, output_path)
    cohort_path = output_path.with_name(output_path.stem + ".cohort.csv")
    cohort_df.to_csv(cohort_path, index=False, encoding="utf-8-sig")
    print(f"[saved cohort effects] {cohort_path}  ({len(cohort_df):,} rows)")

    meta = _make_meta(
        run_id=run_id,
        kind="fit",
        source=source,
        config=cfg,
        disease_ids=list(matrices.keys()),
        sex=sex,
        section=section,
    )
    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved meta] {meta_path}")

    rows_loaded = 0
    cohorts_loaded = 0
    if load_to_db:
        rows_loaded, cohorts_loaded = load_apc_fit_to_db(
            db_path=db_path,
            fit_file=output_path,
            cohort_file=cohort_path,
            meta_json_path=meta_path,
        )

    return {
        "run_id": run_id,
        "output_file": str(output_path),
        "cohort_file": str(cohort_path),
        "meta_file": str(meta_path),
        "rows_loaded": rows_loaded,
        "cohorts_loaded": cohorts_loaded,
        "fits": fits,
    }


# ---------------------------------------------------------------------------
# High-level project
# ---------------------------------------------------------------------------
def run_apc_project(
    *,
    db_path: str | Path,
    fit_file: str | Path,
    long_term_rate: float | None = None,
    convergence_year: int | None = None,
    horizon_year: int | None = None,
    last_observed_year: int | None = None,
    cohort_extrapolation: Literal["flat", "last_drift"] = "last_drift",
    output_path: str | Path | None = None,
    run_id: str | None = None,
    load_to_db: bool = True,
) -> dict[str, Any]:
    """Run the Phase 2 project from an APC fit result parquet and save to DB.

    APC projection would require the ``alpha`` / ``beta`` / ``gamma``
    decomposition of the fit, but the output CSV only stores the smoothed
    rates and improvement rates. This function therefore adopts a simple
    strategy of **rebuilding the fit from the fit_file values and projecting**:

    1. Restore rate_smoothed / improvement_smoothed from fit_file
    2. Project with ScaleBBConfig (AP version) (long_term_rate blend)
    3. The existing γ(c) is already stored in scalebb_cohort_effect and is
       reused as-is

    The γ(c) extrapolation (new cohorts in the projection period) is written
    to scalebb_cohort_effect as additional rows (is_observed=0).
    """
    fit_file = Path(fit_file).resolve()
    if not fit_file.exists():
        raise FileNotFoundError(f"fit file not found: {fit_file}")

    meta_path = fit_file.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    apc_cfg_meta: dict = meta.get("apc_config", {})

    long_term_rate = long_term_rate if long_term_rate is not None else apc_cfg_meta.get("long_term_rate", 0.01)
    convergence_year = convergence_year if convergence_year is not None else apc_cfg_meta.get("convergence_year", 2035)
    horizon_year = horizon_year if horizon_year is not None else apc_cfg_meta.get("horizon_year", 2100)

    run_id = run_id or (meta.get("run_id", "") + "_proj") or (
        datetime.now().strftime("%Y%m%dT%H%M%S") + "_apc_proj"
    )
    if output_path is None:
        sex = meta.get("sex", "total")
        output_path = PROJECT_ROOT / "data" / "processed" / f"scalebb_apc_projection_{sex}.parquet"
    output_path = Path(output_path).resolve()

    fit_df = _read_frame(fit_file)
    proj_frames: list[pd.DataFrame] = []
    gamma_extrapolated_frames: list[pd.DataFrame] = []

    keys = ["disease_id", "sex", "section", "source_stream"]
    for grp_key, grp in fit_df.groupby(keys, dropna=False):
        disease_id, sex, section, source_stream = grp_key
        ages = np.sort(grp["age"].unique().astype(int))
        years = np.sort(grp["year"].unique().astype(int))

        def _pivot(col: str) -> np.ndarray:
            piv = (
                grp.pivot_table(index="age", columns="year", values=col, aggfunc="mean")
                .reindex(index=ages, columns=years)
            )
            return piv.to_numpy(dtype=float)

        rate_smoothed = _pivot("rate_smoothed")
        imp_smoothed = _pivot("improvement_smoothed")

        last_obs = int(last_observed_year) if last_observed_year else int(years.max())

        cfg = ScaleBBConfig(
            long_term_rate=float(long_term_rate),
            convergence_year=int(convergence_year),
            horizon_year=int(horizon_year),
            last_observed_year=last_obs,
            lam_row=float(apc_cfg_meta.get("lam_row", 40.0)),
            lam_col=float(apc_cfg_meta.get("lam_col", 40.0)),
        )

        improvement_final, projection_years = build_blended_improvements(
            imp_smoothed, years=years, ages=ages, config=cfg
        )
        base_idx = int(np.where(years == last_obs)[0][0])
        base_rates = rate_smoothed[:, base_idx]
        rate_projected = project_rates(
            base_rates, improvements=improvement_final, base_year=last_obs, years=projection_years
        )

        proj_frames.append(
            _project_to_long(
                disease_id=str(disease_id),
                sex=str(sex),
                section=str(section),
                source_stream=str(source_stream),
                ages=ages,
                projection_years=projection_years,
                improvement_final=improvement_final,
                rate_projected=rate_projected,
                last_obs=last_obs,
                run_id=run_id,
            )
        )
        print(
            f"[apc-project] disease={disease_id} sex={sex} "
            f"project_years={projection_years.min()}-{projection_years.max()}"
        )

    proj_df = pd.concat(proj_frames, ignore_index=True)
    _save_frame(proj_df, output_path)
    meta_out = dict(meta)
    meta_out["run_id"] = run_id
    meta_out["kind"] = "projection"
    meta_out["long_term_rate"] = long_term_rate
    meta_out["convergence_year"] = convergence_year
    meta_out["horizon_year"] = horizon_year
    meta_path_out = output_path.with_suffix(".meta.json")
    meta_path_out.write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    rows_loaded = 0
    if load_to_db:
        rows_loaded = load_apc_projection_to_db(
            db_path=db_path,
            projection_file=output_path,
            meta_json_path=meta_path_out,
        )

    return {
        "run_id": run_id,
        "output_file": str(output_path),
        "rows_loaded": rows_loaded,
    }


# ---------------------------------------------------------------------------
# DB load
# ---------------------------------------------------------------------------
def load_apc_fit_to_db(
    *,
    db_path: str | Path,
    fit_file: str | Path,
    cohort_file: str | Path | None = None,
    meta_json_path: str | Path | None = None,
) -> tuple[int, int]:
    """Upsert an APC fit result into the DB (scalebb_improvement + scalebb_cohort_effect)."""
    fit_df = _read_frame(Path(fit_file))
    if fit_df.empty:
        return 0, 0

    meta = _read_meta(meta_json_path)
    run_id = str(fit_df["run_id"].iloc[0])

    conn = connect(db_path)
    try:
        _upsert_run_row(
            conn,
            run_id=run_id,
            kind="fit",
            fit_df=fit_df,
            meta=meta,
            source_file=str(fit_file),
        )

        cols_imp = [
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
        df_imp = fit_df.copy()
        for c in cols_imp:
            if c not in df_imp.columns:
                df_imp[c] = None
        df_imp = df_imp[cols_imp]
        conn.execute("DELETE FROM scalebb_improvement WHERE run_id = ?", (run_id,))
        _bulk_insert(conn, "scalebb_improvement", df_imp)

        rows_cohort = 0
        if cohort_file and Path(cohort_file).exists():
            cohort_df = pd.read_csv(cohort_file, encoding="utf-8-sig")
            conn.execute(
                "DELETE FROM scalebb_cohort_effect WHERE run_id = ?", (run_id,)
            )
            _bulk_insert(conn, "scalebb_cohort_effect", cohort_df)
            rows_cohort = len(cohort_df)

        conn.commit()
    finally:
        conn.close()
    print(
        f"[apc-load] scalebb_improvement={len(df_imp)} rows, "
        f"scalebb_cohort_effect={rows_cohort} rows (run_id={run_id})"
    )
    return len(df_imp), rows_cohort


def load_apc_projection_to_db(
    *,
    db_path: str | Path,
    projection_file: str | Path,
    meta_json_path: str | Path | None = None,
) -> int:
    """Upsert an APC projection result into scalebb_projection."""
    df = _read_frame(Path(projection_file))
    if df.empty:
        return 0

    meta = _read_meta(meta_json_path)
    run_id = str(df["run_id"].iloc[0])

    conn = connect(db_path)
    try:
        _upsert_run_row(
            conn,
            run_id=run_id,
            kind="projection",
            fit_df=df,
            meta=meta,
            source_file=str(projection_file),
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
        df_out["is_observed"] = df_out["is_observed"].astype(bool).astype(int)
        df_out = df_out[cols]
        conn.execute("DELETE FROM scalebb_projection WHERE run_id = ?", (run_id,))
        _bulk_insert(conn, "scalebb_projection", df_out)
        conn.commit()
    finally:
        conn.close()
    print(f"[apc-load] scalebb_projection={len(df_out)} rows (run_id={run_id})")
    return len(df_out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_matrices(
    *,
    source: str,
    diseases: Iterable[str] | None,
    sex: str,
    section: str,
    age_min: int,
    age_max: int,
    year_min: int | None,
    year_max: int | None,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    if source == "mortality":
        disease_ids = list(diseases) if diseases else [
            "cancer",
            "heart_disease",
            "cerebrovascular",
        ]
        return load_mortality_matrix(
            disease_ids=disease_ids,
            sex=sex,
            age_min=age_min,
            age_max=age_max,
            year_min=year_min,
            year_max=year_max,
        )
    if source == "age_period":
        ages, years, rates = load_age_period_matrix(
            sex=sex,
            section=section,
            age_min=age_min,
            age_max=age_max,
            year_min=year_min,
            year_max=year_max,
        )
        return {"patient_all": (ages, years, rates)}
    raise ValueError(f"unknown source: {source}")


def _fit_to_long(
    fit: Any,
    *,
    disease_id: str,
    sex: str,
    section: str,
    source_stream: str,
    run_id: str,
) -> pd.DataFrame:
    rows: list[dict] = []
    for i, age in enumerate(fit.ages):
        for j, year in enumerate(fit.years):
            rows.append(
                {
                    "run_id": run_id,
                    "source_stream": source_stream,
                    "disease_id": disease_id,
                    "sex": sex,
                    "section": section,
                    "age": int(age),
                    "year": int(year),
                    "rate_observed": _safe_float(fit.rate_observed[i, j]),
                    "rate_smoothed": _safe_float(fit.rate_smoothed[i, j]),
                    "improvement_observed": _safe_float(fit.improvement_observed[i, j]),
                    "improvement_smoothed": _safe_float(fit.improvement_smoothed[i, j]),
                }
            )
    return pd.DataFrame(rows)


def _cohort_to_long(
    fit: Any,
    *,
    disease_id: str,
    sex: str,
    section: str,
    run_id: str,
) -> pd.DataFrame:
    if fit.gamma is None or fit.cohorts is None:
        return pd.DataFrame(
            columns=[
                "run_id",
                "disease_id",
                "sex",
                "section",
                "cohort",
                "gamma",
                "is_observed",
            ]
        )
    rows = []
    for c, g in zip(fit.cohorts, fit.gamma):
        rows.append(
            {
                "run_id": run_id,
                "disease_id": disease_id,
                "sex": sex,
                "section": section,
                "cohort": int(c),
                "gamma": _safe_float(g),
                "is_observed": 1,
            }
        )
    return pd.DataFrame(rows)


def _project_to_long(
    *,
    disease_id: str,
    sex: str,
    section: str,
    source_stream: str,
    ages: np.ndarray,
    projection_years: np.ndarray,
    improvement_final: np.ndarray,
    rate_projected: np.ndarray,
    last_obs: int,
    run_id: str,
) -> pd.DataFrame:
    rows = []
    for i, age in enumerate(ages):
        for j, year in enumerate(projection_years):
            rows.append(
                {
                    "run_id": run_id,
                    "source_stream": source_stream,
                    "disease_id": disease_id,
                    "sex": sex,
                    "section": section,
                    "age": int(age),
                    "year": int(year),
                    "is_observed": int(year <= last_obs),
                    "improvement_final": _safe_float(improvement_final[i, j]),
                    "rate_projected": _safe_float(rate_projected[i, j]),
                }
            )
    return pd.DataFrame(rows)


def _make_meta(
    *,
    run_id: str,
    kind: str,
    source: str,
    config: Any,
    disease_ids: list[str],
    sex: str,
    section: str,
) -> dict:
    cfg_dict: dict = {}
    try:
        cfg_dict = asdict(config)
    except Exception:
        cfg_dict = {
            "lam_row": float(getattr(config, "lam_row", 0)),
            "lam_col": float(getattr(config, "lam_col", 0)),
            "lam_cohort": float(getattr(config, "lam_cohort", 0)),
            "long_term_rate": float(getattr(config, "long_term_rate", 0)),
            "convergence_year": int(getattr(config, "convergence_year", 0)),
            "horizon_year": int(getattr(config, "horizon_year", 0)),
            "covid_mode": str(getattr(config, "covid_mode", "none")),
            "covid_weight": float(getattr(config, "covid_weight", 1.0)),
            "covid_years": list(getattr(config, "covid_years", [])),
        }
    return {
        "run_id": run_id,
        "kind": kind,
        "source": source,
        "diseases": disease_ids,
        "sex": sex,
        "section": section,
        "apc_config": cfg_dict,
        "flavor": "apc",
    }


def _upsert_run_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    kind: str,
    fit_df: pd.DataFrame,
    meta: dict,
    source_file: str | None,
) -> None:
    apc_cfg = meta.get("apc_config", {})
    diseases = (
        ",".join(sorted(fit_df["disease_id"].dropna().astype(str).unique()))
        if "disease_id" in fit_df.columns
        else None
    )
    sex = fit_df["sex"].iloc[0] if "sex" in fit_df.columns and len(fit_df) else None
    section = (
        fit_df["section"].iloc[0] if "section" in fit_df.columns and len(fit_df) else None
    )
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
            meta.get("source", "mortality_apc"),
            diseases,
            sex,
            section,
            int(fit_df["age"].min()) if "age" in fit_df.columns else None,
            int(fit_df["age"].max()) if "age" in fit_df.columns else None,
            int(fit_df["year"].min()) if "year" in fit_df.columns else None,
            int(fit_df["year"].max()) if "year" in fit_df.columns else None,
            apc_cfg.get("long_term_rate"),
            apc_cfg.get("convergence_year"),
            apc_cfg.get("horizon_year"),
            apc_cfg.get("lam_row"),
            apc_cfg.get("lam_col"),
            json.dumps(apc_cfg, ensure_ascii=False, default=str) if apc_cfg else None,
            source_file,
            f"flavor=apc covid_mode={apc_cfg.get('covid_mode', 'none')} "
            f"lam_cohort={apc_cfg.get('lam_cohort')}",
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


def _save_frame(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)
    csv_path = output.with_suffix(".csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[saved] {output}  ({len(df):,} rows)")


def _safe_float(v: object) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


def fetch_cohort_effects(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    disease_id: str | None = None,
    sex: str | None = None,
) -> pd.DataFrame:
    where: list[str] = ["1 = 1"]
    params: list = []
    if run_id:
        where.append("run_id = ?")
        params.append(run_id)
    if disease_id:
        where.append("disease_id = ?")
        params.append(disease_id)
    if sex:
        where.append("sex = ?")
        params.append(sex)
    sql = (
        "SELECT * FROM scalebb_cohort_effect "
        f"WHERE {' AND '.join(where)} ORDER BY disease_id, sex, cohort"
    )
    return pd.read_sql_query(sql, conn, params=params)


__all__ = [
    "run_apc_fit",
    "run_apc_project",
    "load_apc_fit_to_db",
    "load_apc_projection_to_db",
    "fetch_cohort_effects",
]
