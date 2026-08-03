"""High-level Python API for Scale BB (AP) fit / projection.

Extracts ``cmd_fit`` / ``cmd_project`` from the research-side Scale BB
disease script as reusable Python functions.
KDB's ``scalebb.py`` calls these directly without going through a subprocess.

Public API::

    fit_result_to_long(...)        ScaleBBFitResult -> tidy long DataFrame
    projection_result_to_long(...) projected Result -> tidy long DataFrame
    run_fit_to_file(...)           save fit results to parquet/CSV + meta.json
    run_project_to_file(...)       save project results to parquet/CSV + meta.json
"""
from __future__ import annotations

import datetime
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .model import (
    ScaleBBConfig,
    ScaleBBFitResult,
    fit_scale_bb,
    project_scale_bb,
)
from .panels import load_age_period_matrix, load_mortality_matrix


def _make_run_id() -> str:
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%S")


def _write_frame(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".parquet":
        df.to_parquet(output, index=False)
        csv_path = output.with_suffix(".csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"[saved] {output}  ({len(df):,} rows)")
        print(f"[saved] {csv_path}")
    else:
        df.to_csv(output, index=False, encoding="utf-8-sig")
        print(f"[saved] {output}  ({len(df):,} rows)")


def fit_result_to_long(
    fit: ScaleBBFitResult,
    *,
    disease_id: str,
    sex: str,
    source_stream: str,
    section: str = "total",
    run_id: str | None = None,
) -> pd.DataFrame:
    """Expand a ``ScaleBBFitResult`` into a tidy long DataFrame (observed interval only)."""
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
                    "rate_observed": float(fit.rate_observed[i, j])
                    if np.isfinite(fit.rate_observed[i, j])
                    else None,
                    "rate_smoothed": float(fit.rate_smoothed[i, j])
                    if np.isfinite(fit.rate_smoothed[i, j])
                    else None,
                    "improvement_observed": float(fit.improvement_observed[i, j])
                    if np.isfinite(fit.improvement_observed[i, j])
                    else None,
                    "improvement_smoothed": float(fit.improvement_smoothed[i, j])
                    if np.isfinite(fit.improvement_smoothed[i, j])
                    else None,
                }
            )
    return pd.DataFrame(rows)


def projection_result_to_long(
    fit: ScaleBBFitResult,
    *,
    disease_id: str,
    sex: str,
    source_stream: str,
    section: str = "total",
    run_id: str | None = None,
) -> pd.DataFrame:
    """Expand a projected ``ScaleBBFitResult`` into a long DataFrame (full period)."""
    if fit.projection_years is None or fit.improvement_final is None:
        raise ValueError("fit has no projection; call project_scale_bb first")
    rows: list[dict] = []
    for i, age in enumerate(fit.ages):
        for j, year in enumerate(fit.projection_years):
            rate_proj = (
                float(fit.rate_projected[i, j])
                if fit.rate_projected is not None
                and np.isfinite(fit.rate_projected[i, j])
                else None
            )
            rows.append(
                {
                    "run_id": run_id,
                    "source_stream": source_stream,
                    "disease_id": disease_id,
                    "sex": sex,
                    "section": section,
                    "age": int(age),
                    "year": int(year),
                    "is_observed": bool(
                        year <= fit.config.last_observed_year
                        if fit.config.last_observed_year is not None
                        else year <= fit.years.max()
                    ),
                    "improvement_final": float(fit.improvement_final[i, j])
                    if np.isfinite(fit.improvement_final[i, j])
                    else None,
                    "rate_projected": rate_proj,
                }
            )
    return pd.DataFrame(rows)


def run_fit_to_file(
    *,
    output: str | Path,
    source: str = "mortality",
    diseases: Iterable[str] | None = None,
    sex: str = "total",
    section: str = "total",
    age_min: int = 20,
    age_max: int = 89,
    year_min: int | None = None,
    year_max: int | None = None,
    lam_row: float | None = None,
    lam_col: float | None = None,
    long_term_rate: float | None = None,
    convergence_year: int | None = None,
    horizon_year: int | None = None,
    last_observed_year: int | None = None,
    run_id: str | None = None,
) -> dict:
    """Run Scale BB Phase 1 (fit) and write parquet/CSV + meta.json.

    Returns:
        {'run_id', 'output_file', 'meta_file', 'rows'}
    """
    cfg_kw: dict = {}
    if lam_row is not None:
        cfg_kw["lam_row"] = float(lam_row)
    if lam_col is not None:
        cfg_kw["lam_col"] = float(lam_col)
    if long_term_rate is not None:
        cfg_kw["long_term_rate"] = float(long_term_rate)
    if convergence_year is not None:
        cfg_kw["convergence_year"] = int(convergence_year)
    if horizon_year is not None:
        cfg_kw["horizon_year"] = int(horizon_year)
    if last_observed_year is not None:
        cfg_kw["last_observed_year"] = int(last_observed_year)
    cfg = ScaleBBConfig(**cfg_kw)

    run_id = run_id or _make_run_id()
    frames: list[pd.DataFrame] = []
    meta_entries: list[dict] = []

    if source == "mortality":
        disease_ids = (
            list(diseases) if diseases else ["cancer", "heart_disease", "cerebrovascular"]
        )
        matrices = load_mortality_matrix(
            disease_ids=disease_ids,
            sex=sex,
            age_min=age_min,
            age_max=age_max,
            year_min=year_min,
            year_max=year_max,
        )
        if not matrices:
            raise RuntimeError("no valid disease matrix loaded from mortality panel")
        for did, (ages, years, rates) in matrices.items():
            print(
                f"[fit] disease={did} sex={sex} "
                f"n_age={len(ages)} n_year={len(years)} "
                f"year_range={years.min()}-{years.max()}"
            )
            result = fit_scale_bb(rates, ages=ages, years=years, config=cfg)
            df = fit_result_to_long(
                result,
                disease_id=did,
                sex=sex,
                source_stream=f"mortality_apc/{did}",
                section="total",
                run_id=run_id,
            )
            frames.append(df)
            meta_entries.append(
                {
                    "disease_id": did,
                    "sex": sex,
                    "source_stream": f"mortality_apc/{did}",
                    "age_range": [int(ages.min()), int(ages.max())],
                    "year_range": [int(years.min()), int(years.max())],
                    "config": asdict(cfg),
                }
            )
    elif source == "age_period":
        ages, years, rates = load_age_period_matrix(
            sex=sex,
            section=section,
            age_min=age_min,
            age_max=age_max,
            year_min=year_min,
            year_max=year_max,
        )
        if ages.size == 0 or years.size == 0:
            raise RuntimeError("empty matrix from age_period panel")
        print(
            f"[fit] age_period sex={sex} section={section} "
            f"n_age={len(ages)} n_year={len(years)}"
        )
        result = fit_scale_bb(rates, ages=ages, years=years, config=cfg)
        df = fit_result_to_long(
            result,
            disease_id="patient_all",
            sex=sex,
            source_stream=f"age_period/{section}",
            section=section,
            run_id=run_id,
        )
        frames.append(df)
        meta_entries.append(
            {
                "disease_id": "patient_all",
                "sex": sex,
                "source_stream": f"age_period/{section}",
                "age_range": [int(ages.min()), int(ages.max())],
                "year_range": [int(years.min()), int(years.max())],
                "config": asdict(cfg),
            }
        )
    else:
        raise ValueError(f"unknown source: {source}")

    combined = pd.concat(frames, ignore_index=True)
    output_path = Path(output)
    _write_frame(combined, output_path)

    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {"run_id": run_id, "entries": meta_entries},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[saved] {meta_path}")
    return {
        "run_id": run_id,
        "output_file": str(output_path),
        "meta_file": str(meta_path),
        "rows": len(combined),
    }


def run_project_to_file(
    *,
    fit_file: str | Path,
    output: str | Path,
    long_term_rate: float | None = None,
    convergence_year: int | None = None,
    horizon_year: int | None = None,
    last_observed_year: int | None = None,
    lam_row: float | None = None,
    lam_col: float | None = None,
    run_id: str | None = None,
) -> dict:
    """Run Scale BB Phase 2 (project) and write parquet/CSV + meta.json."""
    fit_path = Path(fit_file)
    if not fit_path.exists():
        raise FileNotFoundError(f"fit file not found: {fit_path}")
    if fit_path.suffix == ".parquet":
        fit_df = pd.read_parquet(fit_path)
    else:
        fit_df = pd.read_csv(fit_path)

    cfg_kw: dict = {}
    if lam_row is not None:
        cfg_kw["lam_row"] = float(lam_row)
    if lam_col is not None:
        cfg_kw["lam_col"] = float(lam_col)
    if long_term_rate is not None:
        cfg_kw["long_term_rate"] = float(long_term_rate)
    if convergence_year is not None:
        cfg_kw["convergence_year"] = int(convergence_year)
    if horizon_year is not None:
        cfg_kw["horizon_year"] = int(horizon_year)
    if last_observed_year is not None:
        cfg_kw["last_observed_year"] = int(last_observed_year)
    cfg_base = ScaleBBConfig(**cfg_kw)
    run_id = run_id or _make_run_id()

    frames: list[pd.DataFrame] = []
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

        rate_matrix = _pivot("rate_smoothed")
        imp_matrix = _pivot("improvement_smoothed")

        last_obs = (
            int(last_observed_year) if last_observed_year else int(years.max())
        )
        cfg = ScaleBBConfig(
            long_term_rate=cfg_base.long_term_rate,
            convergence_year=cfg_base.convergence_year,
            last_observed_year=last_obs,
            lam_row=cfg_base.lam_row,
            lam_col=cfg_base.lam_col,
            diff_order=cfg_base.diff_order,
            age_taper_start=cfg_base.age_taper_start,
            age_taper_end=cfg_base.age_taper_end,
            horizon_year=cfg_base.horizon_year,
        )
        synth_result = ScaleBBFitResult(
            ages=ages,
            years=years,
            rate_observed=_pivot("rate_observed"),
            rate_smoothed=rate_matrix,
            improvement_observed=_pivot("improvement_observed"),
            improvement_smoothed=imp_matrix,
            config=cfg,
        )
        synth_result = project_scale_bb(synth_result, base_year=last_obs)
        df_out = projection_result_to_long(
            synth_result,
            disease_id=disease_id,
            sex=sex,
            source_stream=source_stream,
            section=section,
            run_id=run_id,
        )
        frames.append(df_out)
        print(
            f"[project] disease={disease_id} sex={sex} section={section} "
            f"ages={ages.min()}-{ages.max()} "
            f"years={synth_result.projection_years.min()}-"
            f"{synth_result.projection_years.max()}"
        )

    combined = pd.concat(frames, ignore_index=True)
    output_path = Path(output)
    _write_frame(combined, output_path)
    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_fit": str(fit_path),
                "config": asdict(cfg_base),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[saved] {meta_path}")
    return {
        "run_id": run_id,
        "output_file": str(output_path),
        "meta_file": str(meta_path),
        "rows": len(combined),
    }


__all__ = [
    "fit_result_to_long",
    "projection_result_to_long",
    "run_fit_to_file",
    "run_project_to_file",
]
